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

from dal import autocomplete, forward
from django import forms
from django.contrib.auth.models import Group as UsersGroup
from django.core.exceptions import ValidationError
from django.http import QueryDict
from ensembl.production.djcore.forms import TrimmedCharField

from ensembl.production.dbcopy.models import RequestJob, HostGroup, TargetHostGroup

logger = logging.getLogger(__name__)


class TrimmedCharSelectField(forms.MultipleChoiceField):
    def to_python(self, value):
        if not value:
            return []
        elif not isinstance(value, (list, tuple)):
            raise ValidationError(self.error_messages['invalid_list'], code='invalid_list')
        return ",".join(value)

    def validate(self, value):
        """Validate that the input is a list or tuple."""
        if self.required and not value:
            raise ValidationError(self.error_messages['required'], code='required')


class RequestJobForm(forms.ModelForm):
    class Meta:
        model = RequestJob
        exclude = ('job_id', 'tgt_directory', 'global_status')
        fields = ('src_host', 'tgt_host', 'email_list', 'username',
                  'src_incl_db', 'src_skip_db', 'src_incl_tables', 'src_skip_tables', 'tgt_db_name',
                  'skip_optimize', 'wipe_target', 'convert_innodb', 'dry_run', 'global_status')

    username = forms.CharField(widget=forms.HiddenInput)

    src_host = forms.CharField(
        label="Source Host ",
        help_text="host:port",
        required=True,
        widget=autocomplete.ListSelect2(url='ensembl_dbcopy:src-host-autocomplete',

                                        attrs={'data-placeholder': 'Source host',
                                               'data-minimum-input-length': 2})
    )

    tgt_host = TrimmedCharSelectField(
        label="Target Hosts",
        help_text="List of target hosts",
        required=True,
        widget=autocomplete.Select2Multiple(url='ensembl_dbcopy:tgt-host-autocomplete',
                                            attrs={'data-placeholder': 'Target(s)',
                                                   'data-result-html': True})
    )

    src_incl_db = TrimmedCharField(
        label="Databases to copy",
        help_text='db1,db2,.. or %variation_99% ',
        max_length=2048,
        required=False,
        widget=autocomplete.TagSelect2(url='ensembl_dbcopy:host-db-autocomplete',
                                       forward=[forward.Field('src_host', 'db_host')],
                                       attrs={'data-placeholder': 'Included Db(s)'})
    )

    src_skip_db = TrimmedCharField(
        label="Databases to exclude",
        help_text='db1,db2 or %mart%',
        max_length=2048,
        required=False,
        widget=autocomplete.TagSelect2(url='ensembl_dbcopy:host-db-autocomplete',
                                       forward=[forward.Field('src_host', 'db_host')],
                                       attrs={'data-placeholder': 'Skip table(s)'})
    )

    src_incl_tables = TrimmedCharField(
        label="Only Copy these tables",
        help_text='table1,table2,..',
        max_length=2048,
        required=False,
        widget=autocomplete.TagSelect2(url='ensembl_dbcopy:host-db-table-autocomplete',
                                       forward=[forward.Field('src_host', 'db_host'),
                                                forward.Field('src_incl_db')],
                                       attrs={'data-placeholder': 'Include table(s)'})
    )

    src_skip_tables = TrimmedCharField(
        label="Skip these tables",
        help_text='table1,table2,..',
        max_length=2048,
        required=False,
        widget=autocomplete.TagSelect2(url='ensembl_dbcopy:host-db-table-autocomplete',
                                       forward=[forward.Field('src_host', 'db_host'),
                                                forward.Field('src_incl_db')],
                                       attrs={'data-placeholder': 'Exclude table(s)'})
    )

    tgt_db_name = TrimmedCharField(
        label="Rename DB(s)on target(s)",
        help_text='db1,db2,..',
        max_length=2048,
        widget=forms.TextInput(attrs={'size': 50}),
        required=False)

    email_list = TrimmedCharField(
        label="Email(s)",
        help_text='Comma separated mail list',
        max_length=2048)

    def __init__(self, *args, **kwargs):
        super(RequestJobForm, self).__init__(*args, **kwargs)
        querydict = args[0] if args else kwargs.get('initial', QueryDict())
        if querydict.get('src_host', None) is not None:
            self.fields['src_host'].initial = querydict.get('src_host')
            self.fields['src_host'].widget.choices = [(querydict.get('src_host'), querydict.get('src_host'))]
        if querydict.get('tgt_host', None) is not None:
            tgt_hosts = querydict.get('tgt_host')
            self.fields['tgt_host'].initial = tgt_hosts
            self.fields['tgt_host'].choices = [(val, val) for val in tgt_hosts]
        target_host_group_list = TargetHostGroup.objects.target_host_group_for_user(self.user)
        if len(target_host_group_list) >= 1:
            tgt_group_host = forms.TypedChoiceField(required=False,
                                                    choices=target_host_group_list,
                                                    empty_value='--select target group--')
            tgt_group_host.widget.attrs = {'onblur': "targetHosts()"}
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
