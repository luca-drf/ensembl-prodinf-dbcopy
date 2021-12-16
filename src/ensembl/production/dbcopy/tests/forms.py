from http import HTTPStatus

from django.test import TestCase

from ensembl.production.dbcopy.models import RequestJob


class RequestJobFormTest(TestCase):
    fixtures = ['ensembl_dbcopy']

    def testRequestJobValid(self):
        job = RequestJob.objects.get(job_id='ddbdc15a-07af-11ea-bdcd-9801a79243a5')
        job.status = 'Processing Requests'
        job.save()
        form_data = {
            "src_host": job.src_host,
            "src_incl_db": job.src_incl_db,
            "tgt_host": job.tgt_host,
            "tgt_db_name": job.tgt_db_name,
            "username": "testuser"
        }
        print(form_data)
        logged = self.client.login(username='testuser', password='testgroup123')
        self.assertTrue(logged)
        response = self.client.post("/ensembl_dbcopy/requestjob/add/", data=form_data)
        self.assertEqual(response.status_code, HTTPStatus.OK)
