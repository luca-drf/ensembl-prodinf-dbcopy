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
from collections import OrderedDict

from dal import autocomplete, forward
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group as UsersGroup
from ensembl.production.djcore.forms import TrimmedCharField

from ensembl.production.dbcopy.models import RequestJob, HostGroup, Host, TargetHostGroup

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


class RequestJobForm(forms.ModelForm):
    class Meta:
        model = RequestJob
        exclude = ('job_id', 'tgt_directory', 'overall_status')
        fields = ('src_host', 'tgt_host', 'email_list', 'username',
                  'src_incl_db', 'src_skip_db', 'src_incl_tables', 'src_skip_tables', 'tgt_db_name',
                  'skip_optimize', 'wipe_target', 'convert_innodb', 'dry_run', 'overall_status')

    username = forms.CharField(widget=forms.HiddenInput)

    src_host = forms.CharField(
        label="Source Host ",
        help_text="host:port",
        widget=autocomplete.ListSelect2(url='ensembl_dbcopy:src-host-autocomplete',
                                        attrs={'data-placeholder': 'Source host'})
    )

    tgt_host = TrimmedCharField(
        label="Target Hosts",
        help_text="List of target hosts",
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
        max_length=2048)

    def __init__(self, *args, **kwargs):
        super(RequestJobForm, self).__init__(*args, **kwargs)
        print("Instance", self.instance)
#        if self.instance.pk:
#            self.fields['src_host'].initial = self.instance.src_host
#            self.fields['src_host'].widget.choices = [(self.instance.src_host, self.instance.src_host)]
#        else:
#            print("No instance !")
#            if 'overall_status' in self.fields:
#                del self.fields['overall_status']

        target_host_group_list = _target_host_group(self.user)
        if len(target_host_group_list) >= 1:
            tgt_group_host = forms.TypedChoiceField(required=False,
                                                    choices=target_host_group_list,
                                                    empty_value='--select target group--')
            tgt_group_host.widget.attrs = {'onchange': "targetHosts()"}
            tgt_group_host.label = 'Host Target HostGroup'
            tgt_group_host.help_text = "Select HostGroup to autofill the target host"
            self.fields['tgt_group_host'] = tgt_group_host
            self.fields.move_to_end('tgt_group_host')


class GroupInlineForm(forms.ModelForm):
    class Meta:
        model = HostGroup
        fields = ('group_name',)

    group_name = forms.ModelChoiceField(queryset=UsersGroup.objects.all().order_by('name'), to_field_name='name',
                                        empty_label='Please Select', required=True)
