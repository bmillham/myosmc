
import env
import os
import unittest
from mock import patch
from lib.myspeedtest.myspeedtest import MySpeedtest, MyHttpDownloader, LabelController

mock_client = {'isp': 'mocked.my', 'ip': 'm.o.c.k'}

class mySpeedtestTest(unittest.TestCase):

    def mock_get_config(self):
        self.config['client'] = mock_client
        return self.config

    def test_using_url(self):
        url = 'http://test.url/'
        self.mst = MySpeedtest(url=url)
        self.assertEqual(self.mst.best['url'], url)

    @patch('lib.myspeedtest.myspeedtest.MySpeedtest.get_config', mock_get_config)
    def test_no_url(self):
        self.mst = MySpeedtest()
        self.assertEqual(self.mst.config['client'], mock_client)

    def test_with_no_unit_setting(self):
        mydl = MyHttpDownloader
        self.assertEqual(mydl.units, ('bit', 1))

    def test_with_unit_set_to_byte(self):
        mydl = MyHttpDownloader
        mydl.units = ('bytes', 8)
        self.assertEqual(mydl.units, ('bytes', 8))

    def test_myhttpdownloader_run(self):
        try:
            MyHttpDownloader(0, None, 0, 0).run()
        except:
            self.fail('MyHttpDownloader(1, None, 0, 0).run() failed')

    def test_labelcontroller_update(self):
        mydl = MyHttpDownloader(0, None, 0, 0)
        try:
            mydl.update('thread', 0, 0, 0)
        except:
            self.fail('LabelController.update() failed')
