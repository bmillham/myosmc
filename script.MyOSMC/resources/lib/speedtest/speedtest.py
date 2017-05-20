#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import division, print_function
import os
import re
import csv
import sys
import math
import errno
import signal
import socket
import timeit
import time
import datetime
import platform
import xml.parsers.expat

try:
    import gzip
    GZIP_BASE = gzip.GzipFile
except ImportError:
    print("Unable to import gzip")
    gzip = None
    GZIP_BASE = object

import json
import xml.etree.cElementTree as ET
from urllib2 import urlopen, Request, HTTPError, URLError
from httplib import HTTPConnection
from httplib import HTTPSConnection
from Queue import Queue
from urlparse import urlparse
from urlparse import parse_qs
from hashlib import md5
from cStringIO import StringIO
BytesIO = None

import ssl
try:
    CERT_ERROR = (ssl.CertificateError,)
except AttributeError:
    CERT_ERROR = tuple()
HTTP_ERRORS = ((HTTPError, URLError, socket.error, ssl.SSLError) +
               CERT_ERROR)

SCHEME = 'http'
__version__ = '0.1'


class SpeedTestRequest(object):
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
            uh = urlopen(request)
            return uh, False
        except HTTP_ERRORS:
            e = get_exception()
            return None, e


    def get_response_stream(self, response):
        """Helper function to return either a Gzip reader if
        ``Content-Encoding`` is ``gzip`` otherwise the response itself

        """

        try:
            getheader = response.headers.getheader
        except AttributeError:
            getheader = response.getheader

        if getheader('content-encoding') == 'gzip':
            return GzipDecodedResponse(response)

        return response


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

    def __init__(self, download=0, upload=0, ping=0, server=None):
        self.download = download
        self.upload = upload
        self.ping = ping
        if server is None:
            self.server = {}
        else:
            self.server = server
        self._share = None
        self.timestamp = '%sZ' % datetime.datetime.utcnow().isoformat()
        self.bytes_received = 0
        self.bytes_sent = 0

    def __repr__(self):
        return repr(self.dict())

    def share(self):
        """POST data to the speedtest.net API to obtain a share results
        link
        """

        if self._share:
            return self._share

        download = int(round(self.download / 1000.0, 0))
        ping = int(round(self.ping, 0))
        upload = int(round(self.upload / 1000.0, 0))

        # Build the request to send results back to speedtest.net
        # We use a list instead of a dict because the API expects parameters
        # in a certain order
        api_data = [
            'recommendedserverid=%s' % self.server['id'],
            'ping=%s' % ping,
            'screenresolution=',
            'promo=',
            'download=%s' % download,
            'screendpi=',
            'upload=%s' % upload,
            'testmethod=http',
            'hash=%s' % md5(('%s-%s-%s-%s' %
                             (ping, upload, download, '297aae72'))
                            .encode()).hexdigest(),
            'touchscreen=none',
            'startmode=pingselect',
            'accuracy=1',
            'bytesreceived=%s' % self.bytes_received,
            'bytessent=%s' % self.bytes_sent,
            'serverid=%s' % self.server['id'],
        ]

        headers = {'Referer': 'http://c.speedtest.net/flash/speedtest.swf'}
        request = build_request('://www.speedtest.net/api/api.php',
                                data='&'.join(api_data).encode(),
                                headers=headers)
        f, e = catch_request(request)
        if e:
            raise ShareResultsConnectFailure(e)

        response = f.read()
        code = f.code
        f.close()

        if int(code) != 200:
            raise ShareResultsSubmitFailure('Could not submit results to '
                                            'speedtest.net')

        qsargs = parse_qs(response.decode())
        resultid = qsargs.get('resultid')
        if not resultid or len(resultid) != 1:
            raise ShareResultsSubmitFailure('Could not submit results to '
                                            'speedtest.net')

        self._share = 'http://www.speedtest.net/result/%s.png' % resultid[0]

        return self._share

    def dict(self):
        """Return dictionary of result data"""

        return {
            'download': self.download,
            'upload': self.upload,
            'ping': self.ping,
            'server': self.server,
            'timestamp': self.timestamp,
            'bytes_sent': self.bytes_sent,
            'bytes_received': self.bytes_received,
            'share': self._share,
        }

    def csv(self, delimiter=','):
        """Return data in CSV format"""

        data = self.dict()
        out = StringIO()
        writer = csv.writer(out, delimiter=delimiter, lineterminator='')
        row = [data['server']['id'], data['server']['sponsor'],
               data['server']['name'], data['timestamp'],
               data['server']['d'], data['ping'], data['download'],
               data['upload']]
        writer.writerow([to_utf8(v) for v in row])
        return out.getvalue()

    def json(self, pretty=False):
        """Return data in JSON format"""

        kwargs = {}
        if pretty:
            kwargs.update({
                'indent': 4,
                'sort_keys': True
            })
        return json.dumps(self.dict(), **kwargs)

class SpeedTest(object):
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
        if gzip:
            headers['Accept-Encoding'] = 'gzip'
        request = self.speed_request.build_request('://www.speedtest.net/speedtest-config.php',
                                headers=headers)
        uh, e = self.speed_request.catch_request(request)
        if e:
            print("Failed to get config")
            #raise ConfigRetrievalError(e)
        configxml = []

        stream = self.speed_request.get_response_stream(uh)

        while 1:
            configxml.append(stream.read(1024))
            if len(configxml[-1]) == 0:
                break
        stream.close()
        uh.close()

        if int(uh.code) != 200:
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
        a = (math.sin(dlat / 2) * math.sin(dlat / 2) +
             math.cos(math.radians(lat1)) *
             math.cos(math.radians(lat2)) * math.sin(dlon / 2) *
             math.sin(dlon / 2))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        d = radius * c

        return d


    def get_servers(self, servers=None):
        """Retrieve a the list of speedtest.net servers, optionally filtered
        to servers matching those specified in the ``servers`` argument
        """
        if servers is None:
            servers = []

        self.servers.clear()

        for i, s in enumerate(servers):
            try:
                servers[i] = int(s)
            except ValueError:
                raise InvalidServerIDType('%s is an invalid server type, must '
                                          'be int' % s)

        urls = [
            '://www.speedtest.net/speedtest-servers-static.php',
            'http://c.speedtest.net/speedtest-servers-static.php',
            '://www.speedtest.net/speedtest-servers.php',
            'http://c.speedtest.net/speedtest-servers.php',
        ]

        headers = {}
        if gzip:
            headers['Accept-Encoding'] = 'gzip'

        errors = []
        for url in urls:
            try:
                request = self.speed_request.build_request('%s?threads=%s' %
                                        (url,
                                         self.config['threads']['download']),
                                        headers=headers)
                uh, e = self.speed_request.catch_request(request)
                if e:
                    errors.append('%s' % e)
                    raise ServersRetrievalError()

                stream = self.speed_request.get_response_stream(uh)

                serversxml = []
                while 1:
                    serversxml.append(stream.read(1024))
                    if len(serversxml[-1]) == 0:
                        break

                stream.close()
                uh.close()

                if int(uh.code) != 200:
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
                        d = self.distance(self.lat_lon,
                                     (float(attrib.get('lat')),
                                      float(attrib.get('lon'))))
                    except:
                        continue

                    attrib['d'] = d

                    try:
                        self.servers[d].append(attrib)
                    except KeyError:
                        self.servers[d] = [attrib]

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
                    if urlparts[0] == 'https':
                        h = HTTPSConnection(urlparts[1])
                    else:
                        h = HTTPConnection(urlparts[1])
                    headers = {'User-Agent': self.speed_request.user_agent}
                    start = timeit.default_timer()
                    h.request("GET", urlparts[2], headers=headers)
                    r = h.getresponse()
                    total = (timeit.default_timer() - start)
                except HTTP_ERRORS:
                    e = get_exception()
                    print('%r' % e)
                    cum.append(3600)
                    continue

                text = r.read(9)
                if int(r.status) == 200 and text == 'test=test'.encode():
                    cum.append(total)
                else:
                    cum.append(3600)
                h.close()

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

        for d in sorted(self.servers.keys()):
            for s in self.servers[d]:
                self.closest.append(s)
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

        request_count = len(urls)
        results = []
        times = []

        for i, url in enumerate(urls):
            print('Download: ', url)
            request = self.speed_request.build_request(url, bump=i)
            f = urlopen(request)
            
            start = timeit.default_timer()
            result = f.read()
            stop = timeit.default_timer()

            times.append(stop - start)
            results.append(len(result))
            f.close()

        self.results.bytes_received = sum(results)
        self.results.download = (
            (self.results.bytes_received / (sum(times))) * 8.0
        )
        if self.results.download > 100000:
            self.config['threads']['upload'] = 8
        return self.results.download


if __name__ == '__main__':
    units = ('bit', 1) # ('bytes', 8)
    st = SpeedTest()
    print('Testing from %(isp)s (%(ip)s)...' % st.config['client'])
    print('Retrieving speedtest.net server list...')
    st.get_servers()
    print('Selecting best server based on ping...')
    st.get_best_server()
    print('Hosted by %(sponsor)s (%(name)s) [%(d)0.2f km]: '
            '%(latency)s ms' % st.results.server)
    print('Testing download speed')
    st.download()
    print('Download: %0.2f M%s/s' %
                ((st.results.download / 1000.0 / 1000.0) / units[1],
                 units[0]))
