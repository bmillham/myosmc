#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" License stuff goes here """

import speedtest
import timeit
import threading
from urllib2 import urlopen
import sys

SHUTDOWN_EVENT = speedtest.FakeShutdownEvent()

class MetaClass(type):
    """ A metaclass so we can set the units on a class """

    _units = ('bit', 1)

    @property
    def units(cls):
        """Report units"""
        return cls._units

    @units.setter
    def units(cls, value):
        """Report units"""
        cls._units = value


class LabelController(object):
    """ Example of how updating Kodi could be implimented """

    control = None
    start_time = None
    update_time = None
    running_total = 0
    blip = 0
    wait = 1000
    reset = True

    def update(cls, threadname, total_downloaded, start=None, current=None):
        """How labels may be updated"""

        # Get the units from the myHttpDownload class
        units = cls._units

        if LabelController.reset:
            # the first call will reset all the class variables
            LabelController.start_time = start
            LabelController.update_time = start
            LabelController.running_total = 0
            LabelController.blip = 0
            LabelController.reset = False


        if not LabelController.blip % LabelController.wait:
            now = timeit.default_timer()

            total_speed = (total_downloaded / (now - start))
            total_speed = round((total_speed / 1000.0 / 1000.0) / units[1], 2)

            diff_bytes = total_downloaded - LabelController.running_total
            LabelController.running_total = total_downloaded
            running_speed = (diff_bytes / (now - LabelController.update_time))
            LabelController.update_time = now
            running_speed = round((running_speed / 1000.0 / 1000.0) / units[1], 2)

            # sanity check on the running speed
            if (total_speed * 0.5) > running_speed or (total_speed * 2.0) < running_speed:
                running_speed = total_speed

            sys.stdout.flush()

            sys.stdout.write('%0.2fM%s/s  %0.2fM%s/s  thread: %s - time: %s\n'  % \
                (total_speed, units[0], running_speed, units[0], threadname, now))


        LabelController.blip += 1


class MyHttpDownloader(speedtest.HTTPDownloader, LabelController):
    """ Class to allow sending periodic updates to Kodi """

    # Class variables are shared by all instances of the class
    # These would need to be reset to zero when the test is restarted.
    __metaclass__ = MetaClass # So we can change the units
    total_downloaded = 0

    def __init__(self, i, request, start, timeout):

        threading.Thread.__init__(self)
        self.request = request
        self.result = [0]
        self.starttime = start
        self.timeout = timeout
        self.i = i


    def run(self):
        try:
            current_time = timeit.default_timer()
            elapsed = (current_time - self.starttime)
            if elapsed <= self.timeout:
                f = urlopen(self.request)
                while not SHUTDOWN_EVENT.isSet() and elapsed <= self.timeout:
                    readbytes = len(f.read(10240))
                    self.result.append(readbytes)
                    if self.result[-1] == 0:
                        break

                    with threading.Lock():
                        # This all takes place with locks on the variables.
                        # That prevents other threads from operating on these things
                        # until the lock is released.
                        # This isn't the GIL, so all other python stuff is running
                        # along concurrently.
                        MyHttpDownloader.total_downloaded += (readbytes * 8.0)
                        super(MyHttpDownloader, self).update(
                            threadname=self.i,
                            total_downloaded=MyHttpDownloader.total_downloaded,
                            start=self.starttime,
                            current=current_time
                            )
                f.close()
        except IOError:
            pass


class MySpeedtest(speedtest.Speedtest):
    """ Override Speedtest init to handle a custom test url """

    def __init__(self, config=None, url=None):
        if url is None:
            super(MySpeedtest, self).__init__()
        else:
            self.config = {'sizes': {'download': [1]},
                           'counts': {'download': 1},
                           'threads': {'download': 2},
                           'length': {'download': 1},
                           'client': {'isp': 'Not Checked',
                                      'ip': 'Unknown'},
                           'server': {'sponsor': 'User defined',
                                      'name': 'User defined',
                                      'd': 0,
                                      'latency': 'Unknown'}

                          }
            self.servers = {}
            self.closest = []
            self.best = {'url': url}

            self.results = speedtest.SpeedtestResults()


if __name__ == '__main__':

    speedtest.HTTPDownloader = MyHttpDownloader

    units = ('bit', 1)
    url = None

    for arg in sys.argv:
        if arg == '--bytes':
            units = ('byte', 8)
        if arg.startswith('--url='):
            url = arg.split('=')[1]
            if not url.endswith('/'):
                url += '/'


    speedtest.HTTPDownloader.units = units

    sys.argv.append('--simple')
    sys.argv.append('--no-upload')

    st = MySpeedtest(url=url)
    print 'Testing from %(isp)s (%(ip)s)...' % st.config['client']
    if url is None:
        print 'Retrieving speedtest.net server list...'
        st.get_servers()
        print 'Selecting best server based on ping...'
        st.get_best_server()
        print 'Hosted by %(sponsor)s (%(name)s) [%(d)0.2f km]: %(latency)s ms' % st.results.server
    else:
        print 'Hosted by user selected url:', url
        print 'The full url tested will be:', url + 'random1x1.jpg'

    st.download()
    print('Download: %0.2f M%s/s' %
          ((st.results.download / 1000.0 / 1000.0) / units[1],
           units[0]))


