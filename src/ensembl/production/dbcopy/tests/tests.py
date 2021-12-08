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

import json

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from ensembl.production.dbcopy.models import RequestJob

User = get_user_model()


class RequestJobTest(APITestCase):
    """ Test module for RequestJob model """
    fixtures = ['ensembl_dbcopy']

    # Test requestjob endpoint
    def testRequestJobGetAll(self):
        response = self.client.get(reverse('dbcopy_api:requestjob-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def testCreateRequestJob(self):
        response = self.client.post(reverse('dbcopy_api:requestjob-list'),
                                    {'src_host': 'mysql-ens-sta-1:4519', 'src_incl_db': 'homo_sapiens_core_99_38',
                                     'tgt_host': 'mysql-ens-general-dev-1:4484', 'user': 'testuser'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        las_rq_job = RequestJob.objects.all().order_by('-request_date').first()
        self.assertEqual("mysql-ens-sta-1:4519", las_rq_job.src_host)
        self.assertEqual("mysql-ens-general-dev-1:4484", las_rq_job.tgt_host)
        self.assertIn('job_id', response.data)
        # Test user email set default
        self.assertEqual("testuser@ensembl.org", las_rq_job.email_list)
        self.assertEqual("testuser", las_rq_job.user.username)

    def testCreateRequestJobBadRequest(self):
        response = self.client.post(reverse('dbcopy_api:requestjob-list'),
                                    {'src_host': '', 'src_incl_db': 'homo_sapiens_core_99_38',
                                     'tgt_host': 'mysql-ens-general-dev-1:3306'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('src_host', response.data)
        self.assertIn('user', response.data)
        self.assertEqual('blank', response.data['src_host'][0].code)
        self.assertEqual('required', response.data['user'][0].code)

    def testCreateRequestJobBadRequestEquivalentRunning(self):
        job = RequestJob.objects.get(job_id='ddbdc15a-07af-11ea-bdcd-9801a79243a5')
        job.status = 'Processing Requests'
        job.save()
        params = {
            "src_host": job.src_host,
            "src_incl_db": job.src_incl_db,
            "tgt_host": job.tgt_host,
            "tgt_db_name": job.tgt_db_name,
        }
        active_equivalent_jobs = list(filter(lambda x: x.is_active, RequestJob.objects.equivalent_jobs(**params)))
        self.assertEqual(len(active_equivalent_jobs), 1)
        response = self.client.post(reverse('dbcopy_api:requestjob-list'), params)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        error = response.json()["error"]
        job_id = response.json()["job_id"]
        self.assertRegex(error, r"^A job with the same parameters")
        self.assertEqual(job_id, job.job_id)

    def testCreateRequestJobEquivalentNotRunning(self):
        job = RequestJob.objects.get(job_id='ddbdc15a-07af-11ea-bdcd-9801a79243a5')
        job.status = 'Transfer Ended'
        job.save()
        params = {
            "src_host": job.src_host,
            "src_incl_db": job.src_incl_db,
            "tgt_host": job.tgt_host,
            "tgt_db_name": job.tgt_db_name,
        }
        active_equivalent_jobs = list(filter(lambda x: x.is_active, RequestJob.objects.equivalent_jobs(**params)))
        self.assertEqual(len(active_equivalent_jobs), 0)
        response = self.client.post(reverse('dbcopy_api:requestjob-list'),
                                    {**params, "user": "testuser"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def testCreateRequestJobEquivalentThreeParamsRunning(self):
        job = RequestJob.objects.get(job_id='ddbdc15a-07af-11ea-bdcd-9801a79243a5')
        job.status = 'Processing Requests'
        job.save()
        params = {
            "src_host": job.src_host,
            "src_incl_db": job.src_incl_db,
            "tgt_host": job.tgt_host,
        }
        active_equivalent_jobs = list(filter(lambda x: x.is_active, RequestJob.objects.equivalent_jobs(**params)))
        self.assertEqual(len(active_equivalent_jobs), 0)
        response = self.client.post(reverse('dbcopy_api:requestjob-list'),
                                    {**params, "user": "testuser"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def testCreateRequestJobUser(self):
        response = self.client.post(reverse('dbcopy_api:requestjob-list'),
                                    {'src_host': 'mysql-ens-sta-1:4519', 'src_incl_db': 'homo_sapiens_core_99_38',
                                     'tgt_host': 'mysql-ens-general-dev-1:4484', 'user': 'testuser'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        las_rq_job = RequestJob.objects.all().order_by('-request_date').first()
        self.assertEqual("testuser", las_rq_job.user.username)

    def testCreateRequestJobWrongUser(self):
        response = self.client.post(reverse('dbcopy_api:requestjob-list'),
                                    {'src_host': 'mysql-ens-sta-1:4519', 'src_incl_db': 'homo_sapiens_core_99_38',
                                     'tgt_host': 'mysql-ens-general-dev-1:4484', 'user': 'inexistantuser'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual('invalid', response.data['user'][0].code)

    def testGetRequestJob(self):
        response = self.client.get(
            reverse('dbcopy_api:requestjob-detail', kwargs={'job_id': '8f084180-07ae-11ea-ace0-9801a79243a5'}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def testGetRequestJobNotFound(self):
        response = self.client.get(
            reverse('dbcopy_api:requestjob-detail', kwargs={'job_id': 'd662656c-0a18-11ea-ab6c-9801a79243a5'}))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def testGetRequestJobDetail(self):
        response = self.client.get(
            reverse('dbcopy_api:requestjob-detail', kwargs={'job_id': 'ddbdc15a-07af-11ea-bdcd-9801a79243a5'}))
        response_dict = json.loads(response.content.decode('utf-8'))
        self.assertIn('transfer_logs', response_dict)

    def testPutRequestJob(self):
        response = self.client.put(
            reverse('dbcopy_api:requestjob-detail', kwargs={'job_id': '8f084180-07ae-11ea-ace0-9801a79243a5'}),
            {'src_host': 'mysql-ens-sta-1:4519', 'src_incl_db': 'homo_sapiens_core_99_38',
             'tgt_host': 'mysql-ens-general-dev-2:4586,mysql-ens-general-dev-1:4484,', 'user': 'testuser'})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def testPatchRequestJob(self):
        response = self.client.patch(
            reverse('dbcopy_api:requestjob-detail', kwargs={'job_id': '8f084180-07ae-11ea-ace0-9801a79243a5'}),
            {'src_incl_db': 'homo_sapiens_funcgen_99_38'})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def testDeleteRequestJob(self):
        response = self.client.delete(
            reverse('dbcopy_api:requestjob-detail', kwargs={'job_id': '8f084180-07ae-11ea-ace0-9801a79243a5'}))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        job = RequestJob.objects.filter(job_id='8f084180-07ae-11ea-ace0-9801a79243a5').count()
        # job has actually been deleted from DB
        self.assertEqual(0, job)

    def testDeleteRequestJobNotFound(self):
        response = self.client.delete(
            reverse('dbcopy_api:requestjob-detail', kwargs={'job_id': '673f3b10-09e6-11ea-9206-9801a79243a5'}))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def testDeleteRequestJobNotAcceptable(self):
        req = RequestJob.objects.get(job_id='ddbdc15a-07af-11ea-bdcd-9801a79243a5')
        req.status = 'Processing Requests'
        req.save()
        response = self.client.delete(
            reverse('dbcopy_api:requestjob-detail', kwargs={'job_id': 'ddbdc15a-07af-11ea-bdcd-9801a79243a5'}))
        self.assertEqual(response.status_code, status.HTTP_406_NOT_ACCEPTABLE)

    # Test Source host endpoint
    def testSourceHostGet(self):
        response = self.client.get(reverse('dbcopy_api:srchost-detail', kwargs={'name': 'mysql-ens-sta-1'}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def testSourceHostGetNotFound(self):
        response = self.client.get(reverse('dbcopy_api:srchost-detail', kwargs={'name': 'mysql-ens-compara-2'}))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def testSourceHostGetMultiple(self):
        # Test getting 2 mysql-ens-sta-2 servers
        response = self.client.get(reverse('dbcopy_api:srchost-list'), {'name': 'mysql-ens-sta'})
        self.assertEqual(len(response.data), 2)
        # Test getting mysql-ens-general-dev-1 server
        response = self.client.get(reverse('dbcopy_api:srchost-list'), {'name': 'mysql-ens-general'})
        self.assertIsInstance(json.loads(response.content.decode('utf-8')), list)
        self.assertEqual(len(response.data), 2)

    # Test Target host endpoint
    def testTargetHostGet(self):
        logged = self.client.login(username='testuser', password='testgroup123')
        self.assertTrue(logged)
        response = self.client.get(reverse('dbcopy_api:tgthost-detail', kwargs={'name': 'mysql-ens-sta-1'}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def testTargetHostGetNotFound(self):
        logged = self.client.login(username='testuser', password='testgroup123')
        self.assertTrue(logged)
        response = self.client.get(reverse('dbcopy_api:tgthost-detail', kwargs={'name': 'mysql-ens-compara-2'}))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def testTargetHostGetMultipleWithAllowedUser(self):
        logged = self.client.login(username='testuser', password='testgroup123')
        self.assertTrue(logged)
        # Test getting 2 mysql-ens-sta servers with allowed user
        response = self.client.get(reverse('dbcopy_api:tgthost-list'), {'name': 'mysql-ens-sta'})
        self.assertEqual(len(response.data), 2)

    def testTargetHostGetMultipleWithNonAllowedUser(self):
        # Test getting 2 mysql-ens-sta servers with non-allowed user
        User.objects.get(username='testuser2')
        self.client.login(username='testuser2', password='testgroup1234')
        response = self.client.get(reverse('dbcopy_api:tgthost-list'), {'name': 'mysql-ens-sta'})
        self.assertEqual(len(response.data), 1)

    def testTargetHostGetMultipleServers(self):
        # Test getting mysql-ens-general-dev-1 server
        response = self.client.get(reverse('dbcopy_api:tgthost-list'), {'name': 'mysql-ens-general'})
        self.assertEqual(len(response.data), 2)

    def testRequestModelCleanRaises(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            # test db_name repeated on same target
            RequestJob.objects.create(src_host="host1:3306",
                                      tgt_host="host4:3306,host1:3306",
                                      src_incl_db="db1,db4",
                                      tgt_db_name="db5,db1",
                                      username='testuser')
        with self.assertRaises(ValidationError):
            # test target db name not set at all 9same target dn names
            RequestJob.objects.create(src_host="host1:3306",
                                      tgt_host="host1:3306,host3:3306",
                                      src_incl_db="db1",
                                      username='testuser')
        with self.assertRaises(ValidationError):
            # test target host contains src host and all db selected
            RequestJob.objects.create(src_host="host1:3306",
                                      tgt_host="host2:3306,host1:3306",
                                      username='testuser')
        with self.assertRaises(ValidationError):
            # test target host contains src host and all db selected
            RequestJob.objects.create(tgt_db_name="new_db_name",
                                      tgt_host="host2:3306,host1:3306",
                                      username='testuser')

    def testRequestModelCleanSuccess(self):
        # Test a normal job would pass.
        job = RequestJob.objects.create(src_host="host2:3306",
                                        tgt_host="host4:3306,host3:3306",
                                        src_incl_db="db1,db4",
                                        tgt_db_name="db5,db1",
                                        username='testuser')
        self.assertIsNotNone(job)
        # test a job with same target but different db name would pass
        job = RequestJob.objects.create(src_host="host2:3306",
                                        tgt_host="host2:3306",
                                        src_incl_db="db1",
                                        tgt_db_name="db5",
                                        username='testuser')
        self.assertIsNotNone(job)


class LookupsTest(APITestCase):
    fixtures = ('host_group',)

    def testHostLookup(self):
        response = self.client.get(reverse('ensembl_dbcopy:src-host-autocomplete'))
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)

        self.client.login(username='testusergroup', password='testgroup123')
        response = self.client.get(reverse('ensembl_dbcopy:src-host-autocomplete'))
        # retrieve all
        data = json.loads(response.content)
        self.assertEqual(len(data['results']), 10)
        # filter query
        response = self.client.get(reverse('ensembl_dbcopy:src-host-autocomplete') + '?q=sta-3')
        data = json.loads(response.content)
        self.assertEqual(len(data['results']), 2)

        self.client.login(username='testusergroup2', password='testgroup1234')
        response = self.client.get(reverse('ensembl_dbcopy:tgt-host-autocomplete'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # retrieve all
        data = json.loads(response.content)
        self.assertEqual(len(data['results']), 40)
        # filter query permission should not allow sta as target
        response = self.client.get(reverse('ensembl_dbcopy:tgt-host-autocomplete') + '?q=sta-3')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = json.loads(response.content)
        self.assertEqual(len(data['results']), 0)


class DBIntrospectTest(APITestCase):
    databases = {'default', 'homo_sapiens'}
    fixtures = ('introspect.homo_sapiens.json',)

    def testDatabaseList(self):
        # Test getting test Production dbs
        args = {'host': 'localhost', 'port': 3306}
        response = self.client.get(reverse('dbcopy_api:databaselist', kwargs=args),
                                   {'search': 'test_homo'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 1)
        self.assertEqual(response.data[0], 'test_homo_sapiens')
        response = self.client.get(reverse('dbcopy_api:databaselist',
                                           kwargs={**args, 'host': 'bad-host'}),
                                   {'search': 'test_production_services'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(reverse('dbcopy_api:databaselist', kwargs=args),
                                   {'search': 'no_result_search'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)
        response = self.client.get(reverse('dbcopy_api:databaselist', kwargs=args),
                                   {'matches[]': ['test_homo_sapiens']})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        response = self.client.get(reverse('dbcopy_api:databaselist', kwargs=args),
                                   {'matches[]': ['no_match']})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def testTableList(self):
        args = {'host': 'localhost',
                'port': 3306,
                'database': 'test_homo_sapiens'}
        # Test getting meta_key table for Production dbs
        response = self.client.get(reverse('dbcopy_api:tablelist', kwargs=args),
                                   {'search': 'ass'})
        response_list = json.loads(response.content.decode('utf-8'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_list), 2)
        args['host'] = 'badhost-name'
        response = self.client.get(reverse('dbcopy_api:tablelist', kwargs=args),
                                   {'search': 'meta'})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        args['host'] = 'localhost'
        response = self.client.get(reverse('dbcopy_api:tablelist', kwargs=args),
                                   {'search': 'unknown'})
        response_list = json.loads(response.content.decode('utf-8'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_list), 0)
