from pywb.warcserver.inputrequest import DirectWSGIInputRequest, POSTInputRequest, PostQueryExtractor
from werkzeug.routing import Map, Rule

import webtest
import traceback
from six.moves.urllib.parse import parse_qsl
from io import BytesIO


#=============================================================================
class InputReqApp(object):
    def __init__(self):
        self.url_map = Map()
        self.url_map.add(Rule('/test/<path:url>', endpoint=self.direct_input_request))
        self.url_map.add(Rule('/test-postreq', endpoint=self.post_fullrequest))

    def direct_input_request(self, environ, url=''):
        inputreq = DirectWSGIInputRequest(environ)
        return inputreq.reconstruct_request(url)

    def post_fullrequest(self, environ):
        params = dict(parse_qsl(environ.get('QUERY_STRING', '')))
        inputreq = POSTInputRequest(environ)
        return inputreq.reconstruct_request(params['url'])

    def __call__(self, environ, start_response):
        urls = self.url_map.bind_to_environ(environ)
        try:
            endpoint, args = urls.match()
        except HTTPException as e:
            return e(environ, start_response)

        result = endpoint(environ, **args)
        start_response('200 OK', [('Content-Type', 'text/plain; charset=utf-8')])
        return [result]



#=============================================================================
class TestInputReq(object):
    def setup(self):
        self.app = InputReqApp()
        self.testapp = webtest.TestApp(self.app)

    def test_get_direct(self):
        res = self.testapp.get('/test/http://example.com/', headers={'Foo': 'Bar'})
        assert res.text == '\
GET /test/http://example.com/ HTTP/1.0\r\n\
Host: example.com\r\n\
Foo: Bar\r\n\
\r\n\
'

    def test_post_direct(self):
        res = self.testapp.post('/test/http://example.com/', headers={'Foo': 'Bar'}, params='ABC')
        lines = res.text.split('\r\n')
        assert lines[0] == 'POST /test/http://example.com/ HTTP/1.0'
        assert 'Host: example.com' in lines
        assert 'Content-Length: 3' in lines
        assert 'Content-Type: application/x-www-form-urlencoded' in lines
        assert 'Foo: Bar' in lines

        assert 'ABC' in lines

    def test_post_req(self):
        postdata = '\
GET /example.html HTTP/1.0\r\n\
Foo: Bar\r\n\
\r\n\
'
        res = self.testapp.post('/test-postreq?url=http://example.com/', params=postdata)

        assert res.text == '\
GET /example.html HTTP/1.0\r\n\
Host: example.com\r\n\
Foo: Bar\r\n\
\r\n\
'


class TestPostQueryExtract(object):
    @classmethod
    def setup_class(cls):
        cls.post_data = b'foo=bar&dir=%2Fbaz'

    def test_post_extract_1(self):
        pq = PostQueryExtractor('POST', 'application/x-www-form-urlencoded',
                                len(self.post_data), BytesIO(self.post_data))

        assert pq.append_post_query('http://example.com/') == 'http://example.com/?foo=bar&dir=/baz'

        assert pq.append_post_query('http://example.com/?123=ABC') == 'http://example.com/?123=ABC&foo=bar&dir=/baz'

    def test_post_extract_wrong_method(self):
        pq = PostQueryExtractor('PUT', 'application/x-www-form-urlencoded',
                                len(self.post_data), BytesIO(self.post_data))

        assert pq.append_post_query('http://example.com/') == 'http://example.com/'

    def test_post_extract_non_form_data_1(self):
        pq = PostQueryExtractor('POST', 'application/octet-stream',
                                len(self.post_data), BytesIO(self.post_data))

        #base64 encoded data
        assert pq.append_post_query('http://example.com/') == 'http://example.com/?__wb_post_data=Zm9vPWJhciZkaXI9JTJGYmF6'

    def test_post_extract_non_form_data_2(self):
        pq = PostQueryExtractor('POST', 'text/plain',
                                len(self.post_data), BytesIO(self.post_data))

        #base64 encoded data
        assert pq.append_post_query('http://example.com/pathbar?id=123') == 'http://example.com/pathbar?id=123&__wb_post_data=Zm9vPWJhciZkaXI9JTJGYmF6'

    def test_post_extract_length_invalid_ignore(self):
        pq = PostQueryExtractor('POST', 'application/x-www-form-urlencoded',
                                0, BytesIO(self.post_data))

        assert pq.append_post_query('http://example.com/') == 'http://example.com/'

        pq = PostQueryExtractor('POST', 'application/x-www-form-urlencoded',
                                'abc', BytesIO(self.post_data))

        assert pq.append_post_query('http://example.com/') == 'http://example.com/'

    def test_post_extract_length_too_short(self):
        pq = PostQueryExtractor('POST', 'application/x-www-form-urlencoded',
                                len(self.post_data) - 4, BytesIO(self.post_data))

        assert pq.append_post_query('http://example.com/') == 'http://example.com/?foo=bar&dir=%2'

    def test_post_extract_length_too_long(self):
        pq = PostQueryExtractor('POST', 'application/x-www-form-urlencoded',
                                len(self.post_data) + 4, BytesIO(self.post_data))

        assert pq.append_post_query('http://example.com/') == 'http://example.com/?foo=bar&dir=/baz'


