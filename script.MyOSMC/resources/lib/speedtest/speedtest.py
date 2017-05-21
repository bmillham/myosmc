#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""speedtest-osmc: put osmc license and other stuff here"""

from __future__ import division, print_function
import os
import math
import socket
import timeit
import datetime
import platform
import xml.parsers.expat
import sys
import xml.etree.cElementTree as ET
from urllib2 import urlopen, Request, HTTPError, URLError
from httplib import HTTPConnection
from urlparse import urlparse

HTTP_ERRORS = ((HTTPError, URLError, socket.error))

SCHEME = 'http'
__version__ = '0.1'

def get_exception():
    """Helper function to work with py2.4-py3 for getting the current
    exception in a try/except block
    """
    return sys.exc_info()[1]

class SpeedTestRequest(object):
    """A request object that adds user_agent"""
    def __init__(self):
        self._user_agent = None


    def _build_user_agent(self):
        """Build a Mozilla/5.0 compatible User-Agent string"""

        ua_tuple = (
            'Mozilla/5.0',
            '(%s; U; %s; en-us)' % (platform.system(), platform.architecture()[0]),
            'Python/%s' % platform.python_version(),
            '(KHTML, like Gecko)',
            'speedtest-osmc/%s' % __version__
        )
        self._user_agent = ' '.join(ua_tuple)


    @property
    def user_agent(self):
        """Property to return the user_agent"""
        if self._user_agent is None:
            self._build_user_agent()

        return self._user_agent


    def build_request(self, url, data=None, headers=None, bump=''):
        """Build a urllib2 request object

        This function automatically adds a User-Agent header to all requests

        """

        if not self.user_agent:
            self._build_user_agent()

        if not headers:
            headers = {}

        if url[0] == ':':
            schemed_url = '%s%s' % (SCHEME, url)
        else:
            schemed_url = url

        if '?' in url:
            delim = '&'
        else:
            delim = '?'

        # WHO YOU GONNA CALL? CACHE BUSTERS!
        final_url = '%s%sx=%s.%s' % (schemed_url, delim,
                                     int(timeit.time.time() * 1000),
                                     bump)

        headers.update({
            'User-Agent': self._user_agent,
            'Cache-Control': 'no-cache',
        })

        return Request(final_url, data=data, headers=headers)


    def catch_request(self, request):
        """Helper function to catch common exceptions encountered when
        establishing a connection with a HTTP/HTTPS request

        """

        try:
            conn = urlopen(request)
            return conn, False
        except HTTP_ERRORS:
            exc = get_exception()
            return None, exc


class SpeedtestException(Exception):
    """Base exception for this module"""



class SpeedtestBestServerFailure(SpeedtestException):
    """Unable to determine best server"""


class SpeedtestResults(object):
    """Class for holding the results of a speedtest, including:

    Download speed
    Upload speed
    Ping/Latency to test server
    Data about server that the test was run against

    Additionally this class can return a result data as a dictionary or CSV,
    as well as submit a POST of the result data to the speedtest.net API
    to get a share results image link.
    """

    def __init__(self):
        self._download = 0
        self._upload = 0
        self._ping = 0
        self._server = {}
        self._timestamp = '%sZ' % datetime.datetime.utcnow().isoformat()
        self._bytes_received = 0
        self._bytes_sent = 0

    @property
    def bytes_sent(self):
        """Bytes sent during the test"""
        return self._bytes_sent

    @bytes_sent.setter
    def bytes_sent(self, value):
        self._bytes_sent = value

    @property
    def upload(self):
        """Uploaded"""
        return self._upload

    @upload.setter
    def upload(self, value):
        self._upload = value

    @property
    def timestamp(self):
        """When the test was run"""
        return self._timestamp

    @property
    def bytes_received(self):
        """Bytes received from the server"""
        return self._bytes_received

    @bytes_received.setter
    def bytes_received(self, value):
        self._bytes_received = value

    @property
    def download(self):
        """Amount downloaded"""
        return self._download

    @download.setter
    def download(self, value):
        self._download = value

    @property
    def ping(self):
        """Ping time"""
        return self._ping

    @ping.setter
    def ping(self, value):
        self._ping = value

    @property
    def server(self):
        """Speedtest.net server"""
        return self._server

    @server.setter
    def server(self, value):
        self._server = value

    def __repr__(self):
        return repr(self.dict())


    def dict(self):
        """Return dictionary of result data"""

        return {
            'download': self._download,
            'upload': self._upload,
            'ping': self._ping,
            'server': self._server,
            'timestamp': self._timestamp,
            'bytes_sent': self._bytes_sent,
            'bytes_received': self._bytes_received,
        }


class SpeedTest(object):
    """ Perform speedtests using speedtest.net servers """

    def __init__(self, config=None):
        self.speed_request = SpeedTestRequest()
        self.config = {}
        self.get_config()
        if config is not None:
            self.config.update(config)

        self.servers = {}
        self.closest = []
        self.best = {}

        self.results = SpeedtestResults()

    def get_config(self):
        """Download the speedtest.net configuration and return only the data
        we are interested in
        """

        headers = {}

        request = self.speed_request.build_request('://www.speedtest.net/speedtest-config.php',
                                                   headers=headers)
        response, exc = self.speed_request.catch_request(request)
        if exc:
            print("Failed to get config")
            #raise ConfigRetrievalError(e)
        configxml = []

        #stream = self.speed_request.get_response_stream(strm)

        while 1:
            configxml.append(response.read(1024))
            if len(configxml[-1]) == 0:
                break
        response.close()

        if int(response.code) != 200:
            return None

        root = ET.fromstring(''.encode().join(configxml))
        server_config = root.find('server-config').attrib
        download = root.find('download').attrib
        upload = root.find('upload').attrib
        # times = root.find('times').attrib
        client = root.find('client').attrib

        ignore_servers = list(
            map(int, server_config['ignoreids'].split(','))
        )

        ratio = int(upload['ratio'])
        upload_max = int(upload['maxchunkcount'])
        up_sizes = [32768, 65536, 131072, 262144, 524288, 1048576, 7340032]
        sizes = {
            'upload': up_sizes[ratio - 1:],
            'download': [350, 500, 750, 1000, 1500, 2000, 2500,
                         3000, 3500, 4000]
        }

        size_count = len(sizes['upload'])

        upload_count = int(math.ceil(upload_max / size_count))

        counts = {
            'upload': upload_count,
            'download': int(download['threadsperurl'])
        }

        threads = {
            'upload': int(upload['threads']),
            'download': int(server_config['threadcount']) * 2
        }

        length = {
            'upload': int(upload['testlength']),
            'download': int(download['testlength'])
        }

        self.config.update({
            'client': client,
            'ignore_servers': ignore_servers,
            'sizes': sizes,
            'counts': counts,
            'threads': threads,
            'length': length,
            'upload_max': upload_count * size_count
        })

        self.lat_lon = (float(client['lat']), float(client['lon']))

        return self.config

    def distance(self, origin, destination):
        """Determine distance between 2 sets of [lat,lon] in km"""

        lat1, lon1 = origin
        lat2, lon2 = destination
        radius = 6371  # km

        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        calc1 = (math.sin(dlat / 2) * math.sin(dlat / 2) +
                 math.cos(math.radians(lat1)) *
                 math.cos(math.radians(lat2)) * math.sin(dlon / 2) *
                 math.sin(dlon / 2))
        calc2 = 2 * math.atan2(math.sqrt(calc1), math.sqrt(1 - calc1))
        return radius * calc2


    def get_servers(self, servers=None):
        """Retrieve a the list of speedtest.net servers, optionally filtered
        to servers matching those specified in the ``servers`` argument
        """
        if servers is None:
            servers = []

        self.servers.clear()

        for i, srv in enumerate(servers):
            try:
                servers[i] = int(srv)
            except ValueError:
                raise InvalidServerIDType('%s is an invalid server type, must '
                                          'be int' % srv)

        urls = [
            '://www.speedtest.net/speedtest-servers-static.php',
            'http://c.speedtest.net/speedtest-servers-static.php',
            '://www.speedtest.net/speedtest-servers.php',
            'http://c.speedtest.net/speedtest-servers.php',
        ]

        headers = {}

        errors = []
        for url in urls:
            try:
                request = self.speed_request.build_request('%s?threads=%s' %
                                                           (url,
                                                            self.config['threads']['download']),
                                                           headers=headers)
                response, exc = self.speed_request.catch_request(request)
                if exc:
                    errors.append('%s' % exc)
                    raise ServersRetrievalError()

                serversxml = []
                while 1:
                    serversxml.append(response.read(1024))
                    if len(serversxml[-1]) == 0:
                        break

                response.close()

                if int(response.code) != 200:
                    raise ServersRetrievalError()

                #print(''.encode().join(serversxml))

                try:
                    root = ET.fromstring(''.encode().join(serversxml))
                    elements = root.getiterator('server')
                except (SyntaxError, xml.parsers.expat.ExpatError):
                    raise ServersRetrievalError()

                for server in elements:
                    try:
                        attrib = server.attrib
                    except AttributeError:
                        attrib = dict(list(server.attributes.items()))

                    if servers and int(attrib.get('id')) not in servers:
                        continue

                    if int(attrib.get('id')) in self.config['ignore_servers']:
                        continue

                    try:
                        dist = self.distance(self.lat_lon,
                                             (float(attrib.get('lat')),
                                              float(attrib.get('lon'))))
                    except:
                        continue

                    attrib['d'] = dist

                    try:
                        self.servers[dist].append(attrib)
                    except KeyError:
                        self.servers[dist] = [attrib]

                #print ''.encode().join(serversxml)

                break

            except:
                continue

        if servers and not self.servers:
            print("No servers")
            #raise NoMatchedServers()

        return self.servers

    def get_best_server(self, servers=None):
        """Perform a speedtest.net "ping" to determine which speedtest.net
        server has the lowest latency
        """

        if not servers:
            if not self.closest:
                servers = self.get_closest_servers()
            servers = self.closest

        results = {}
        for server in servers:
            cum = []
            url = os.path.dirname(server['url'])
            urlparts = urlparse('%s/latency.txt' % url)
            #print('%s %s/latency.txt' % ('GET', url))
            for _ in range(0, 3):
                try:
                    hconn = HTTPConnection(urlparts[1])
                    headers = {'User-Agent': self.speed_request.user_agent}
                    start = timeit.default_timer()
                    hconn.request("GET", urlparts[2], headers=headers)
                    req = hconn.getresponse()
                    total = (timeit.default_timer() - start)
                except HTTP_ERRORS:
                    exc = get_exception()
                    print('%r' % exc)
                    cum.append(3600)
                    continue

                text = req.read(9)
                if int(req.status) == 200 and text == 'test=test'.encode():
                    cum.append(total)
                else:
                    cum.append(3600)
                hconn.close()

            avg = round((sum(cum) / 6) * 1000.0, 3)
            results[avg] = server

        try:
            fastest = sorted(results.keys())[0]
        except IndexError:
            raise SpeedtestBestServerFailure('Unable to connect to servers to '
                                             'test latency.')
        best = results[fastest]
        best['latency'] = fastest

        self.results.ping = fastest
        self.results.server = best

        self.best.update(best)
        #print(best)
        return best

    def get_closest_servers(self, limit=5):
        """Limit servers to the closest speedtest.net servers based on
        geographic distance
        """

        if not self.servers:
            self.get_servers()

        for dist in sorted(self.servers.keys()):
            for srv in self.servers[dist]:
                self.closest.append(srv)
                if len(self.closest) == limit:
                    break
            else:
                continue
            break

        return self.closest

    def download(self):
        """Test without threads"""

        urls = []
        for size in self.config['sizes']['download']:
            urls.append('%s/random%sx%s.jpg' %
                        (os.path.dirname(self.best['url']), size, size))

        results = []
        times = []

        for i, url in enumerate(urls[:-1]):
            print('Download: ', url)
            request = self.speed_request.build_request(url, bump=i)
            urlstream = urlopen(request)

            start = timeit.default_timer()
            result = urlstream.read()
            stop = timeit.default_timer()

            times.append(stop - start)
            results.append(len(result))
            urlstream.close()

        self.results.bytes_received = sum(results)
        self.results.download = (
            (self.results.bytes_received / (sum(times))) * 8.0
        )
        if self.results.download > 100000:
            self.config['threads']['upload'] = 8
        return self.results.download


if __name__ == '__main__':
    UNITS = ('bit', 1) # ('bytes', 8)
    SPEEDTEST = SpeedTest()
    print('Testing from %(isp)s (%(ip)s)...' % SPEEDTEST.config['client'])
    print('Retrieving speedtest.net server list...')
    SPEEDTEST.get_servers()
    print('Selecting best server based on ping...')
    SPEEDTEST.get_best_server()
    print('Hosted by %(sponsor)s (%(name)s) [%(d)0.2f km]: '
          '%(latency)s ms' % SPEEDTEST.results.server)
    print('Testing download speed')
    SPEEDTEST.download()
    print('Download: %0.2f M%s/s' %
          ((SPEEDTEST.results.download / 1000.0 / 1000.0) / UNITS[1],
           UNITS[0]))
