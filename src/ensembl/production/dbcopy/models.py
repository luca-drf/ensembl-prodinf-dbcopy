#   See the NOTICE file distributed with this work for additional information
#   regarding copyright ownership.
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#       http://www.apache.org/licenses/LICENSE-2.0
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
import logging
import re
import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Count, Q
from django.utils.html import format_html
from ensembl.production.core.db_introspects import get_database_set
from ensembl.production.djcore.forms import EmailListFieldValidator, ListFieldRegexValidator
from ensembl.production.djcore.models import NullTextField

from ensembl.production.dbcopy.filters import get_filter_match

logger = logging.getLogger(__name__)


class Dbs2Exclude(models.Model):
    table_schema = models.CharField(primary_key=True, db_column='TABLE_SCHEMA',
                                    max_length=64)  # Field name made lowercase.

    class Meta:
        db_table = 'dbs_2_exclude'
        app_label = 'ensembl_dbcopy'


class DebugLog(models.Model):
    job_id = models.CharField(max_length=128, blank=True, null=True)
    sequence = models.IntegerField(blank=True, null=True)
    function = models.CharField(max_length=128, blank=True, null=True)
    value = models.TextField(max_length=8192, blank=True, null=True)

    class Meta:
        db_table = 'debug_log'
        app_label = 'ensembl_dbcopy'


class RequestJobManager(models.Manager):

    def get_queryset(self):
        return super().get_queryset().annotate(nb_transfers=Count('transfer_logs')).annotate(
            running_transfers=Count('transfer_logs', filter=Q(end_date__isnull=True)))


class RequestJob(models.Model):
    class Meta:
        db_table = 'request_job'
        app_label = 'ensembl_dbcopy'
        verbose_name = "Copy job"
        verbose_name_plural = "Copy jobs"
        ordering = ('-request_date',)

    job_id = models.CharField(primary_key=True, max_length=128, default=uuid.uuid1, editable=False)
    src_host = models.TextField("Source Host", max_length=2048,
                                validators=[RegexValidator(regex="^[\w-]+:[0-9]{4}",
                                                           message="Source Host should be: host:port")])
    src_incl_db = NullTextField("Included Db(s)", max_length=2048, blank=True, null=True)
    src_skip_db = NullTextField("Skipped Db(s)", max_length=2048, blank=True, null=True)
    src_incl_tables = NullTextField("Included Table(s)", max_length=2048, blank=True, null=True)
    src_skip_tables = NullTextField("Skipped Table(s)", max_length=2048, blank=True, null=True)
    tgt_host = models.TextField("Target Host(s)", max_length=2048,
                                validators=[ListFieldRegexValidator(regex="^[\w-]+:[0-9]{4}",
                                                                    message="Target Hosts should be formatted like this"
                                                                            " host:port or host1:port1,host2:port2")])
    tgt_db_name = NullTextField("Target DbName(s)", max_length=2048, blank=True, null=True)
    tgt_directory = NullTextField(max_length=2048, blank=True, null=True)
    skip_optimize = models.BooleanField("Optimize on target", default=False)
    wipe_target = models.BooleanField("Wipe target", default=False)
    convert_innodb = models.BooleanField("Convert Innodb=>MyISAM", default=False)
    dry_run = models.BooleanField("Dry Run", default=False)
    email_list = models.TextField("Notify Email(s)", max_length=2048, blank=True, null=True,
                                  validators=[EmailListFieldValidator(
                                      message="Email list should contain one or more comma "
                                              "separated valid email addresses.")])
    start_date = models.DateTimeField("Started on", blank=True, null=True, editable=False)
    end_date = models.DateTimeField("Ended on", blank=True, null=True, editable=False)
    username = models.CharField("Submitter", max_length=64, blank=False, null=True, db_column='user')
    status = models.CharField("Status", max_length=20, blank=True, null=True, editable=False)
    request_date = models.DateTimeField("Submitted on", editable=False, auto_now_add=True)

    objects = RequestJobManager()

    running_transfers = 0
    nb_transfers = 0

    def __str__(self):
        tgt_hosts = self.tgt_host.split(',')
        return "%s[%s]:%s -> %s" % (self.username, self.job_id, self.src_host, tgt_hosts[0])

    @property
    def user(self):
        """
        Wrapper to make sure we have a way to retrieve the user from the field
        Assuming username is unique (in case of an overriden default user model)
        :return: User or AnonymousUser
        """
        User = get_user_model()
        try:
            return User.objects.get(username=self.username)
        except ObjectDoesNotExist:
            logger.error("Request job %s has no user attached", self.job_id)
            return AnonymousUser()

    @user.setter
    def user(self, user):
        """
        Set the username field value from the user in parameters
        :param user: User (see django.contrib.auth)
        :return: None
        """
        self.username = user.username

    @property
    def overall_status(self):
        if self.status:
            if (self.end_date and self.status == 'Transfer Ended') or 'Try:' in self.status:
                if self.running_transfers > 0:
                    return 'Failed'
                else:
                    return 'Complete'
            elif self.running_transfers > 0 and self.status == 'Processing Requests':
                return 'Running'
            elif self.status == 'Processing Requests' or self.status == 'Creating Requests':
                return 'Scheduled'
        return 'Submitted'

    @property
    def done_transfers(self):
        return self.nb_transfers - self.running_transfers

    @property
    def progress(self):
        if self.nb_transfers > 0:
            return format((self.done_transfers / self.nb_transfers) * 100, ".1f")
        return 0.0

    @property
    def detailed_status(self):
        total_tables = self.nb_transfers
        # .count()
        # table_copied = self.table_copied
        status_msg = 'Submitted'
        if self.status == 'Processing Requests' or self.status == 'Creating Requests':
            status_msg = 'Scheduled'
        if self.progress == 100.0 and self.status == 'Transfer Ended':
            status_msg = 'Complete'
        elif total_tables > 0:
            if self.status:
                if (self.end_date and self.status == 'Transfer Ended') or ('Try:' in self.status):
                    status_msg = 'Failed'
                elif self.status == 'Processing Requests':
                    status_msg = 'Running'
        return {'status_msg': status_msg,
                # 'table_copied': table_copied,
                'table_copied': self.done_transfers,
                'total_tables': total_tables,
                'progress': self.progress}

    #    @property
    #    def table_copied(self):
    #        nbr_tables = sum(map(lambda log: 1 if log.end_date else 0, self.transfer_logs.all()))
    #        return nbr_tables

    def _clean_db_set_for_filters(self, from_host, field):
        host = from_host.split(':')[0]
        port = from_host.split(':')[1]
        name_filter, name_matches = get_filter_match(getattr(self, field))
        try:
            src_db_set = get_database_set(hostname=host, port=port,
                                          name_filter=name_filter,
                                          name_matches=name_matches,
                                          excluded_schemas=Dbs2Exclude.objects.values_list('table_schema', flat=True))
            if len(src_db_set) == 0:
                raise ValidationError({'src_incl_db': 'No db matching incl. [%s %s] ' % (name_filter, name_matches)})
        except ValueError as e:
            raise ValidationError({field: str(e)})

    def clean_src_incl_db(self):
        if self.src_host and self.src_incl_db:
            self._clean_db_set_for_filters(self.src_host, 'src_incl_db')

    def clean_src_skip_db(self):
        if self.src_skip_db and self.tgt_db_name:
            raise ValidationError({'src_skip_db': 'Field "Names of databases on Target Host" is not empty. \n'
                                                  'You can\'t both skip and rename at the same time. \n'
                                                  'Consider clear this field.'})
        if self.src_host and self.src_skip_db:
            self._clean_db_set_for_filters(self.src_host, 'src_skip_db')

    def clean_tgt_host(self):
        """
        Clean tgt_host fiels
        :return: None
        :raise: ValidationError
        """
        from ensembl.production.core.db_introspects import get_database_set

        if self.src_host in self.tgt_host:

            hostname, port = self.src_host.split(':')
            try:
                present_dbs = get_database_set(hostname, port,
                                               excluded_schemas=Dbs2Exclude.objects.values_list('table_schema',
                                                                                                flat=True))
            except ValueError as e:
                raise ValidationError({'src_host': 'Invalid source hostname or port'},
                                      'invalid')
            src_names = present_dbs
            if self.src_incl_db:
                src_names = _apply_db_names_filter(_text_field_as_set(self.src_incl_db), src_names)
            if self.src_skip_db:
                skip_names = _apply_db_names_filter(_text_field_as_set(self.src_skip_db), present_dbs)
                src_names = src_names.difference(skip_names)

            if self.tgt_db_name:
                tgt_conflicts = _text_field_as_set(self.tgt_db_name).intersection(src_names)
                if tgt_conflicts:
                    raise ValidationError({'tgt_db_name': 'Some source and target databases coincide. '
                                                          'Please change conflicting target names'})
            elif src_names:
                raise ValidationError({'src_incl_db': 'Some source and target databases coincide. '
                                                      'Please add target names or change sources'})

    def clean_tgt_db_name(self):
        """
        Clean target db names
        :return: None
        :raise: ValidationError
        """
        incl_db = _text_field_as_set(self.src_incl_db)
        tgt_db = _text_field_as_set(self.tgt_db_name)
        if tgt_db:
            if len(tgt_db) != len(incl_db):
                raise ValidationError(
                    {'tgt_db_name': "The number of databases to copy should match the number of databases \n"
                                    "renamed on target hosts"}, 'invalid')
            for dbname in incl_db:
                if '%' in dbname:
                    raise ValidationError({'tgt_db_name': "You can't rename a pattern"}, "invalid")

    def clean_wipe_target(self):
        """
        Check wipe target values
        :return: None
        :raise: ValidationError
        """
        from ensembl.production.core.db_introspects import get_engine, get_schema_names
        incl_db = _text_field_as_set(self.src_incl_db)
        tgt_db_names = _text_field_as_set(self.tgt_db_name)
        new_db_names = _text_field_as_set(self.tgt_db_name) if self.tgt_db_name else incl_db
        if (self.wipe_target is False) and (not self.src_incl_tables) and new_db_names:
            for tgt_host in self.tgt_host:
                hostname, port = tgt_host.split(':')
                try:
                    db_engine = get_engine(hostname, port)
                except RuntimeError as e:
                    raise ValidationError({'tgt_host': 'Invalid host: %(tgt_host)s'}, 'invalid',
                                          {'tgt_host', tgt_host})
                tgt_present_db_names = set(get_schema_names(db_engine))
                if tgt_present_db_names.intersection(new_db_names):
                    field_name = 'tgt_db_name' if tgt_db_names else 'src_incl_db'
                    raise ValidationError({field_name: 'One or more database names already present on'
                                                       ' the target. Consider enabling Wipe target option.'}, 'invalid')

    def clean_username(self):
        """not exactly cleaning the username field, but check that user had the permission to perform the
        copy request
        :return: None
        :raise: ValidationError
        """
        for tgt_host in self.tgt_host:
            hostname = tgt_host.split(':')[0]
            hosts = Host.objects.filter(name=hostname)
            if not hosts:
                raise ValidationError({'tgt_host': "%(hostname)s is not present in our system"},
                                      'invalid',
                                      {'hostname': hostname})
            group = HostGroup.objects.filter(host_id=hosts[0].auto_id)
            if group:
                host_groups = group.values_list('group_name', flat=True)
                user_groups = self.user.groups.values_list('name', flat=True)
                common_groups = set(host_groups).intersection(set(user_groups))
                if not common_groups and not self.user.is_superuser:
                    raise ValidationError({'tgt_host': "You are not allowed to copy to %(hostname)s"},
                                          'forbidden',
                                          {'hostname': hostname})

    def clean(self):
        """
        Main Object clean
        :raise: ValidationError
        :return: None
        """
        targets = self.tgt_host.split(',')
        src_dbs = self.src_incl_db.split(',') if self.src_incl_db else []
        tgt_dbs = self.tgt_db_name.split(',') if self.tgt_db_name else []
        one_src_db_targets = bool(set(src_dbs).intersection(tgt_dbs)) or len(tgt_dbs) == 0 or len(src_dbs) == 0
        if self.src_host in targets and one_src_db_targets:
            raise ValidationError({'tgt_host': "You can't set a copy with identical source/target host/db pair.\n"
                                               "Please rename target or change target host"},
                                  'forbidden')
        super().clean()

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        """ Override default save.
        Enforce clean to be called on every save
        """
        if not self.email_list and self.username:
            self.email_list = ','.join([user + "@ebi.ac.uk" for user in self.username.split(',')])
        self.full_clean()
        super().save(force_insert, force_update, using, update_fields)

    @property
    def completion(self):
        return format_html(
            '''
            <progress value="{0}" max="100"></progress>
            <span style="font-weight:bold">{0}%</span>
            ''',
            self.progress
        )


class TransferLog(models.Model):
    class Meta:
        db_table = 'transfer_log'
        unique_together = (('job_id', 'tgt_host', 'table_schema', 'table_name'),)
        app_label = 'ensembl_dbcopy'
        verbose_name = 'TransferLog'

    auto_id = models.BigAutoField(primary_key=True)
    job_id = models.ForeignKey(RequestJob, db_column='job_id', on_delete=models.CASCADE, related_name='transfer_logs')
    tgt_host = models.CharField(max_length=512, editable=False)
    table_schema = models.CharField(db_column='TABLE_SCHEMA', max_length=64,
                                    editable=False)  # Field name made lowercase.
    table_name = models.CharField(db_column='TABLE_NAME', max_length=64, editable=False)  # Field name made lowercase.
    renamed_table_schema = models.CharField(max_length=64, editable=False)
    target_directory = models.TextField(max_length=2048, blank=True, null=True, editable=False)
    start_date = models.DateTimeField(blank=True, null=True, editable=False)
    end_date = models.DateTimeField(blank=True, null=True, editable=False)
    size = models.BigIntegerField(blank=True, null=True, editable=False)
    retries = models.IntegerField(blank=True, null=True, editable=False)
    message = models.CharField(max_length=255, blank=True, null=True, editable=False)

    @property
    def table_status(self):
        if self.end_date:
            return 'Complete'
        elif self.job_id.status:
            if (self.job_id.end_date and self.job_id.status == 'Transfer Ended') or ('Try:' in self.job_id.status):
                return 'Failed'
            elif self.job_id.status == 'Processing Requests':
                return 'Running'
        return 'Submitted'


def clean_host_pattern(pattern):
    if ":" in pattern:
        pattern = pattern.split(':')[0]
    return pattern


class HostManager(models.Manager):

    def qs_tgt_host_for_user(self, pattern, user, active=True):
        """
        Retrieve available target host for the specified user, in form of a QuerySet
        :param active: filter only active ones
        :param pattern: str pattern to look for
        :param user: request user to filter targets permission
        :return:
        """
        host_queryset = self.all()
        group_queryset = HostGroup.objects.all()
        if pattern:
            host_queryset = host_queryset.filter(name__icontains=clean_host_pattern(pattern)).order_by(
                'name')
        if active:
            host_queryset = host_queryset.filter(active=True)
        for host in host_queryset:
            group = group_queryset.filter(host_id=host.auto_id)
            if group:
                host_groups = group.values_list('group_name', flat=True)
                user_groups = user.groups.values_list('name', flat=True)
                common_groups = set(host_groups).intersection(set(user_groups))
                if not common_groups:
                    host_queryset = host_queryset.exclude(name=host.name)
        return host_queryset

    def qs_src_host(self, pattern, active=True):
        host_queryset = self.all()
        if pattern:
            host_queryset = host_queryset.filter(name__icontains=clean_host_pattern(pattern)).order_by('name')
        if active:
            host_queryset = host_queryset.filter(active=True)
        return host_queryset


class Host(models.Model):
    class Meta:
        db_table = 'server_host'
        unique_together = (('name', 'port'),)
        app_label = 'ensembl_dbcopy'
        verbose_name = 'Host'
        ordering = ('name',)

    objects = HostManager()

    auto_id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=64)
    port = models.IntegerField()
    mysql_user = models.CharField(max_length=64)
    virtual_machine = models.CharField(max_length=255, blank=True, null=True)
    mysqld_file_owner = models.CharField(max_length=128, null=True, blank=True)
    active = models.BooleanField(default=True, blank=False)

    def __str__(self):
        return '{}:{}'.format(self.name, self.port)


class TargetHostGroupManager(models.Manager):

    def target_host_group_for_user(self, user):
        # get groups, current user belongs to
        user_groups = user.groups.values_list('name', flat=True)
        logger.debug("User Groups %s", user_groups)
        # get all host user can copy  based on assigned group
        user_hosts_ids = Host.objects.filter(targethostgroup__target_group_name__in=list(user_groups)).values_list(
            'auto_id', flat=True)
        logger.debug("User Hosts Ids %s", user_hosts_ids)

        # get all host names that target group contains
        target_host_dict = {}
        for each_group in self.all():
            target_host_dict[each_group.target_group_name] = ''
            for each_host in each_group.target_host.all():
                target_host_dict[each_group.target_group_name] += each_host.name + ':' + str(each_host.port) + ','

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('Target_host_dict %s', target_host_dict)
            logger.debug('TargetHostGroup %s', TargetHostGroup.objects.all())
        target_groups = list(set([(target_host_dict[group.target_group_name], group.target_group_name)
                                  for group in self.filter(target_host__auto_id__in=list(user_hosts_ids))
                                  ]))
        return target_groups


class TargetHostGroup(models.Model):
    class Meta:
        db_table = 'target_host_group'
        app_label = 'ensembl_dbcopy'
        verbose_name = 'Hosts Target HostGroup'

    objects = TargetHostGroupManager()
    target_group_id = models.BigAutoField(primary_key=True)
    target_group_name = models.CharField('Hosts HostGroup', max_length=80, unique=True)
    target_host = models.ManyToManyField('Host')

    def __str__(self):
        return '{}'.format(self.target_group_name)


class HostGroup(models.Model):
    class Meta:
        db_table = 'host_group'
        app_label = 'ensembl_dbcopy'
        verbose_name = 'Host HostGroup'

    group_id = models.BigAutoField(primary_key=True)
    host_id = models.ForeignKey(Host, db_column='auto_id', on_delete=models.CASCADE, related_name='groups')
    group_name = models.CharField('User HostGroup', max_length=80)

    def __str__(self):
        return '{}'.format(self.group_name)


def _apply_db_names_filter(db_names, all_db_names):
    if len(db_names) == 1:
        db_name = db_names.pop()
        filter_re = re.compile(db_name.replace('%', '.*').replace('_', '.'))
        return set(filter(filter_re.search, all_db_names))
    return db_names


def _text_field_as_set(text):
    return set(filter(lambda x: x != '', text.split(',')))
