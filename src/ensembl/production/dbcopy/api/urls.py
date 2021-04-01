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
from django.urls import path, include, re_path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions, routers
from ensembl.production.dbcopy.api import viewsets
from ensembl.production.dbcopy.api.views import ListDatabases, ListTables

schema_view = get_schema_view(
    openapi.Info(
        title="Copy DB API snippets",
        default_version='v1',
        description="Copy DB Api Description",
        contact=openapi.Contact(email="ensembl-production@ebi.ac.uk"),
        license=openapi.License(name="Apache 2 License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

# API router setup
router = routers.SimpleRouter(trailing_slash=False)
# Services URIs configuration

router.register(prefix=r'requestjob',
                viewset=viewsets.RequestJobViewSet,
                basename='requestjob')

router.register(prefix=r'src_host',
                viewset=viewsets.SourceHostViewSet,
                basename='src_host')

router.register(prefix=r'tgt_host',
                viewset=viewsets.TargetHostViewSet,
                basename='tgt_host')

urlpatterns = [
    path('', include(router.urls)),
    re_path('databases/(?P<host>[\w-]+)/(?P<port>\d+)', ListDatabases.as_view(), name='databaselist'),
    re_path('tables/(?P<host>[\w-]+)/(?P<port>\d+)/(?P<database>\w+)', ListTables.as_view(), name='tablelist'),
    re_path('swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path(f'docs/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]
