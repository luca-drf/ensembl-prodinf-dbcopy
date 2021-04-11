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
from collections import OrderedDict

from dal import autocomplete, forward
from django import forms
from django.contrib.auth.models import Group as UsersGroup
from django.core.validators import RegexValidator
from ensembl.production.core.db_introspects import get_engine, get_schema_names
from ensembl.production.djcore.forms import TrimmedCharField, EmailListFieldValidator, ListFieldRegexValidator

from ensembl.production.dbcopy.lookups import get_excluded_schemas
from ensembl.production.dbcopy.models import RequestJob, Group, Host, TargetHostGroup

logger = logging.getLogger(__name__)


def _target_host_group(user):
    # get groups, current user belongs to

    user_groups = user.groups.values_list('name', flat=True)
    logger.debug("User Groups %s", user_groups)
    # get all host user can copy  based on assigned group
    user_hosts_ids = Host.objects.filter(targethostgroup__target_group_name__in=list(user_groups)).values_list(
        'auto_id', flat=True)
    logger.debug("User Hosts Ids %s", user_hosts_ids)

    # get all host names that target group contains
    target_host_dict = {}
    for each_group in TargetHostGroup.objects.all():
        target_host_dict[each_group.target_group_name] = ''
        for each_host in each_group.target_host.all():
            target_host_dict[each_group.target_group_name] += each_host.name + ':' + str(each_host.port) + ','

    logger.debug('Target_host_dict %s', target_host_dict)
    logger.debug('TargetHostGroup %s', TargetHostGroup.objects.all())
    target_groups = list(set([(target_host_dict[group.target_group_name], group.target_group_name)
                              for group in TargetHostGroup.objects.filter(target_host__auto_id__in=list(user_hosts_ids))
                              ]))
    return target_groups


def _text_field_as_set(text):
    return set(filter(lambda x: x != '', text.split(',')))


def _apply_db_names_filter(db_names, all_db_names):
    if len(db_names) == 1:
        db_name = db_names.pop()
        filter_re = re.compile(db_name.replace('%', '.*').replace('_', '.'))
        return set(filter(filter_re.search, all_db_names))
    return db_names


class RequestJobForm(forms.ModelForm):
    class Meta:
        model = RequestJob
        exclude = ('job_id', 'tgt_directory', 'overall_status')
        fields = ('src_host', 'tgt_host', 'email_list', 'username',
                  'src_incl_db', 'src_skip_db', 'src_incl_tables', 'src_skip_tables', 'tgt_db_name',
                  'skip_optimize', 'wipe_target', 'convert_innodb', 'dry_run', 'overall_status')
        widgets = {
            'username': forms.HiddenInput
        }

    src_host = forms.CharField(
        label="Source Host ",
        help_text="host:port",
        required=True,
        validators=[
            RegexValidator(regex="^[\w-]+:[0-9]{4}",
                           message="Source Host should be formatted like this host:port")
        ],
        widget=autocomplete.ListSelect2(url='ensembl_dbcopy:src-host-autocomplete',
                                         attrs={'data-placeholder': 'Source host'})
    )

    tgt_host = TrimmedCharField(
        label="Target Hosts",
        help_text="Host1:port1,Host2:port2",
        required=True,
        validators=[
            ListFieldRegexValidator(regex="^[\w-]+:[0-9]{4}",
                                    message="Target Hosts should be formatted like this"
                                            " host:port or host1:port1,host2:port2")
        ],
        widget=autocomplete.TagSelect2(url='ensembl_dbcopy:tgt-host-autocomplete',
                                       attrs={
                                           'data-placeholder': 'Target(s)',
                                           'data-result-html': True
                                       })
    )

    src_incl_db = TrimmedCharField(
        label="Databases to copy",
        help_text='db1,db2,.. or %variation_99% ',
        max_length=2048,
        required=False,
        widget=autocomplete.TagSelect2(url='ensembl_dbcopy:host-db-autocomplete',
                                       forward=[forward.Field('src_host', 'db_host')])
    )

    src_skip_db = TrimmedCharField(
        label="Databases to exclude",
        help_text='db1,db2 or %mart%',
        max_length=2048,
        required=False,
        widget=autocomplete.TagSelect2(url='ensembl_dbcopy:host-db-autocomplete',
                                       forward=[forward.Field('src_host', 'db_host')]))

    src_incl_tables = TrimmedCharField(
        label="Only Copy these tables",
        help_text='table1,table2,..',
        max_length=2048,
        required=False,
        widget=autocomplete.TagSelect2(url='ensembl_dbcopy:host-db-table-autocomplete',
                                       forward=[forward.Field('src_host', 'db_host'),
                                                forward.Field('src_incl_db')]))
    src_skip_tables = TrimmedCharField(
        label="Skip these tables",
        help_text='table1,table2,..',
        max_length=2048,
        required=False,
        widget=autocomplete.TagSelect2(url='ensembl_dbcopy:host-db-table-autocomplete',
                                       forward=[forward.Field('src_host', 'db_host'),
                                                forward.Field('src_incl_db')]))

    tgt_db_name = TrimmedCharField(
        label="Rename DB(s)on target(s)",
        help_text='db1,db2,..',
        max_length=2048,
        required=False)

    email_list = TrimmedCharField(
        label="Email(s)",
        help_text='Comma separated mail list',
        max_length=2048,
        required=True,
        validators=[
            EmailListFieldValidator(
                message="Email list should contain one or more comma separated valid email addresses."
            )
        ])

    def _validate_db_skipping(self, src_skip_db_names, tgt_db_names):
        if src_skip_db_names and tgt_db_names:
            self.add_error('src_skip_db',
                           'Field "Names of databases on Target Host" is not empty. \n'
                           'Consider clear it, or clear this field.')

    def _validate_db_renaming(self, src_dbs, tgt_dbs):
        if tgt_dbs:
            if len(tgt_dbs) != len(src_dbs):
                self.add_error('tgt_db_name',
                               "The number of databases to copy should match the number of databases \n"
                               "renamed on target hosts")
            for dbname in src_dbs:
                if '%' in dbname:
                    self.add_error('tgt_db_name', "You can't rename a pattern")

    def _validate_source_and_target(self, src_host, tgt_hosts, src_dbs, src_skip_dbs, tgt_db_names):
        from ensembl.production.core.db_introspects import get_database_set
        if src_host in tgt_hosts:
            hostname, port = src_host.split(':')
            try:
                present_dbs = get_database_set(hostname, port, excluded_schemas=get_excluded_schemas())
            except ValueError as e:
                raise forms.ValidationError('Invalid source hostname or port')
            src_names = present_dbs
            if src_dbs:
                src_names = _apply_db_names_filter(src_dbs, src_names)
            if src_skip_dbs:
                skip_names = _apply_db_names_filter(src_skip_dbs, present_dbs)
                src_names = src_names.difference(skip_names)

            if tgt_db_names:
                tgt_conflicts = tgt_db_names.intersection(src_names)
                if tgt_conflicts:
                    raise forms.ValidationError(
                        'Some source and target databases coincide. Please change conflicting target names')
            elif src_names:
                raise forms.ValidationError(
                    'Some source and target databases coincide. Please add target names or change sources')

    def _validate_wipe_target(self, wipe_target, src_dbs, src_skip_dbs, tgt_hosts, tgt_db_names, src_incl_tables):
        src_db_names = src_dbs.difference(src_skip_dbs)
        new_db_names = tgt_db_names if tgt_db_names else src_db_names
        if (wipe_target is False) and (not src_incl_tables) and new_db_names:
            for tgt_host in tgt_hosts:
                hostname, port = tgt_host.split(':')
                try:
                    db_engine = get_engine(hostname, port)
                except RuntimeError as e:
                    self.add_error('tgt_host', 'Invalid host: {}'.format(tgt_host))
                    continue
                tgt_present_db_names = set(get_schema_names(db_engine))
                if tgt_present_db_names.intersection(new_db_names):
                    field_name = 'tgt_db_name' if tgt_db_names else 'src_incl_db'
                    self.add_error(field_name, 'One or more database names already present on'
                                               ' the target. Consider enabling Wipe target option.')
                    break

    def _validate_user_permission(self, tgt_hosts):
        # Checking that user is allowed to copy to the target server.
        for tgt_host in tgt_hosts:
            hostname = tgt_host.split(':')[0]
            hosts = Host.objects.filter(name=hostname)
            if not hosts:
                self.add_error('tgt_host', hostname + " is not present in our system")
                return
            group = Group.objects.filter(host_id=hosts[0].auto_id)
            if group:
                host_groups = group.values_list('group_name', flat=True)
                user_groups = self.user.groups.values_list('name', flat=True)
                common_groups = set(host_groups).intersection(set(user_groups))
                if not common_groups and not self.user.is_superuser:
                    self.add_error('tgt_host', "You are not allowed to copy to " + hostname)

    def clean(self):
        cleaned_data = super().clean()
        src_host = cleaned_data.get('src_host', '')
        wipe_target = cleaned_data.get('wipe_target', False)
        src_incl_tables = cleaned_data.get('src_incl_tables', '')
        tgt_hosts = _text_field_as_set(cleaned_data.get('tgt_host', ''))
        src_dbs = _text_field_as_set(cleaned_data.get('src_incl_db', ''))
        src_skip_dbs = _text_field_as_set(cleaned_data.get('src_skip_db', ''))
        tgt_db_names = _text_field_as_set(cleaned_data.get('tgt_db_name', ''))
        self._validate_db_skipping(src_skip_dbs, tgt_db_names)
        self._validate_db_renaming(src_dbs, tgt_db_names)
        self._validate_source_and_target(src_host, tgt_hosts, src_dbs, src_skip_dbs, tgt_db_names)
        # TODO reactivate this validation when wipe_target is available again
        # self._validate_wipe_target(wipe_target, src_dbs, src_skip_dbs, tgt_hosts, tgt_db_names, src_incl_tables)
        self._validate_user_permission(tgt_hosts)
        return self.cleaned_data

    def __init__(self, *args, **kwargs):
        if 'initial' in kwargs and 'from_request_job' in kwargs['initial']:
            kwargs['instance'] = RequestJob.objects.get(pk=kwargs['initial']['from_request_job'])
        super(RequestJobForm, self).__init__(*args, **kwargs)
        if self.instance:
            self.fields['src_host'].initial = self.instance.src_host
            self.fields['src_host'].widget.choices = [(self.instance.src_host, self.instance.src_host)]
        target_host_group_list = _target_host_group(self.user)
        if len(target_host_group_list) >= 1:
            tgt_group_host = forms.TypedChoiceField(required=False,
                                                    choices=target_host_group_list,
                                                    empty_value='--select target group--')
            tgt_group_host.widget.attrs = {'onchange': "targetHosts()"}
            tgt_group_host.label = 'Host Target Group'
            tgt_group_host.help_text = "Select Group to autofill the target host"

            field_order = list(self.fields.items())
            field_order.insert(5, ("tgt_group_host", tgt_group_host))
            self.fields = OrderedDict(field_order)


class GroupInlineForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ('group_name',)

    group_name = forms.ModelChoiceField(queryset=UsersGroup.objects.all().order_by('name'), to_field_name='name',
                                        empty_label='Please Select', required=True)