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
import django.core.exceptions

from rest_framework import viewsets, mixins, response, status, generics
import rest_framework.exceptions

from ensembl.production.dbcopy.api.serializers import RequestJobSerializer, HostSerializer, TransferLogSerializer
from ensembl.production.dbcopy.models import RequestJob, Host, TransferLog
from rest_framework.permissions import AllowAny

class RequestJobViewSet(mixins.CreateModelMixin,
                        mixins.RetrieveModelMixin,
                        mixins.ListModelMixin,
                        mixins.DestroyModelMixin,
                        viewsets.GenericViewSet):
    serializer_class = RequestJobSerializer
    permission_classes = [AllowAny]

    queryset = RequestJob.objects.all()
    pagination_class = None
    lookup_field = 'job_id'

    def create(self, request, *args, **kwargs):
        params = {
            "src_host",
            "src_incl_db",
            "src_skip_db",
            "src_incl_tables",
            "src_skip_tables",
            "tgt_host",
            "tgt_db_name",
        }
        filters = {k: v for k, v in request.data.items() if k in params and v}
        for job in RequestJob.equivalent_running_jobs(**filters):
            raise rest_framework.exceptions.ValidationError(
                {"error": "A job with the same parameters is already in the system.", "job_id": job.job_id}
            )
        try:
            return super().create(request, *args, **kwargs)
        except django.core.exceptions.ValidationError as err:
            try:
                errors = err.message_dict
            except AttributeError:
                errors = err.messages
            raise rest_framework.exceptions.ValidationError(errors) from err

    def destroy(self, request, *args, **kwargs):
        """
        Only destroy object when status is still "submitted" otherwise raise an error and do not delete object
        :param request:
        :param args:
        :param kwargs:
        :return:
        """
        instance = self.get_object()
        if instance.global_status == 'Submitted':
            self.perform_destroy(instance)
            return response.Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return response.Response(status=status.HTTP_406_NOT_ACCEPTABLE)


class SourceHostViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = HostSerializer
    lookup_field = 'name'

    def get_queryset(self):
        """
        Return a list of hosts according to a keyword
        """
        return Host.objects.qs_src_host(self.request.GET.get('name', self.kwargs.get('name', None)), active=False)


class TargetHostViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = HostSerializer
    lookup_field = 'name'

    def get_queryset(self):
        # WARNING request now need a user to perform the listing. But no use case found outside of Django admin so far.
        return Host.objects.qs_tgt_host_for_user(self.request.GET.get('name', self.kwargs.get('name', None)),
                                                 self.request.user,
                                                 active=False)


class TransferLogView(generics.ListAPIView):
    serializer_class = TransferLogSerializer
    lookup_field = 'job_id'

    def get_queryset(self):
        return TransferLog.objects.filter(job_id=self.kwargs.get('job_id'))
