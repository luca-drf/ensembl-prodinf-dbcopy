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
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers
from rest_framework import status
from rest_framework.exceptions import APIException

from ensembl.production.dbcopy.models import TransferLog, RequestJob, Host

User = get_user_model()


class BaseUserTimestampSerializer(serializers.ModelSerializer):
    username = serializers.CharField(required=True, source='user')

    def validate(self, data):
        if "username" in data:
            try:
                User.objects.get(username=data['username'])
            except ObjectDoesNotExist:
                exc = APIException(code='invalid', detail={"user": ["Unknown user " + data['username']]})
                # hack to update status code. :-(
                exc.status_code = status.HTTP_400_BAD_REQUEST
                raise exc
        data = super().validate(data)
        return data


class TransferLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransferLog
        fields = (
            'job_id',
            'tgt_host',
            'table_schema',
            'table_name',
            'renamed_table_schema',
            'target_directory',
            'start_date',
            'end_date',
            'size',
            'retries',
            'message',
            'table_status')


class RequestJobListSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = RequestJob
        fields = (
            'url',
            'src_host',
            'src_incl_db',
            'src_skip_db',
            'src_incl_tables',
            'src_skip_tables',
            'tgt_host',
            'tgt_db_name',
            'tgt_directory',
            'skip_optimize',
            'wipe_target',
            'convert_innodb',
            'email_list',
            'start_date',
            'end_date',
            'user',
            'overall_status')
        read_only_fields = ['job_id']
        extra_kwargs = {
            'url': {'view_name': 'dbcopy_api:requestjob-detail', 'lookup_field': 'job_id'},
        }

    user = serializers.CharField(required=True, source='username')


class RequestJobDetailSerializer(BaseUserTimestampSerializer):
    class Meta:
        model = RequestJob
        fields = (
            'job_id',
            'transfer_log',
            'src_host',
            'src_incl_db',
            'src_skip_db',
            'src_incl_tables',
            'src_skip_tables',
            'tgt_host',
            'tgt_db_name',
            'tgt_directory',
            'skip_optimize',
            'wipe_target',
            'convert_innodb',
            'email_list',
            'start_date',
            'end_date',
            'user',
            'overall_status',
            'detailed_status')
        read_only_fields = ['job_id']

    transfer_log = TransferLogSerializer(many=True, source='transfer_logs', read_only=True)
    user = serializers.CharField(required=True, source='username')


class HostSerializer(serializers.ModelSerializer):
    class Meta:
        model = Host
        fields = '__all__'
