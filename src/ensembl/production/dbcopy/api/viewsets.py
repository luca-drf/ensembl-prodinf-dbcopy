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
from rest_framework import viewsets, mixins, response, status

from ensembl.production.dbcopy.api.serializers import RequestJobDetailSerializer, RequestJobListSerializer, HostSerializer
from ensembl.production.dbcopy.models import RequestJob, Host, HostGroup


class RequestJobViewSet(mixins.CreateModelMixin,
                        mixins.RetrieveModelMixin,
                        mixins.ListModelMixin,
                        mixins.DestroyModelMixin,
                        viewsets.GenericViewSet):
    serializer_class = RequestJobListSerializer
    queryset = RequestJob.objects.all()
    pagination_class = None
    lookup_field = 'job_id'

    def get_serializer_class(self):
        if self.action == 'list':
            return RequestJobListSerializer
        else:
            return RequestJobDetailSerializer

    def destroy(self, request, *args, **kwargs):
        """
        Only destroy object when status is still "submitted" otherwise raise an error and do not delete object
        :param request:
        :param args:
        :param kwargs:
        :return:
        """
        instance = self.get_object()
        if instance.overall_status == 'Submitted':
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
        return Host.objects.qs_src_host(self.request.query_params.get('name', None))


class TargetHostViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = HostSerializer
    lookup_field = 'name'

    def get_queryset(self):
        return Host.objects.qs_tgt_host_for_user(self.request.query_params.get('name', None), self.request.user)
