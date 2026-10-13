import secrets
import unittest, json, asyncio
from aiohttp import ClientSession, web
from .helpers import payload, request
from custom_components.klar_assist_extensions.klar_client import KlarClient, KlarError, decode_weather, valid_url


class DecodeTests(unittest.TestCase):
    def test_only_supported_contract(self):
        for native in [None, {}, {**payload(), 'schema_version':'3.0'},
                       {**payload(),'decision':{'type':'chat'}}, payload(entity='light.test')]:
            with self.assertRaises(KlarError):
                decode_weather(native)

    def test_no_multiple_steps_or_duplicate_slots(self):
        native=payload()
        native['plan']['steps']*=2
        with self.assertRaises(KlarError): decode_weather(native)
        native=payload()
        native['plan']['steps'][0]['intent']['slots']*=2
        with self.assertRaises(KlarError): decode_weather(native)

    def test_day_and_part_mapping(self):
        for code, number in [('mon',0),('tue',1),('wed',2),('thu',3),('fri',4),('sat',5),('sun',6)]:
            query=decode_weather(payload(day=code))
            self.assertEqual(query.weekday,number)
            self.assertTrue(query.native_time)
        self.assertTrue(decode_weather(payload(part='morning')).unsupported)
        self.assertTrue(decode_weather(payload(day='weekend')).unsupported)

    def test_url_validation(self):
        for url in ['http://localhost:10520','https://host/']:
            self.assertTrue(valid_url(url))
        for url in ['file:///tmp/foo',f'http://user:{secrets.token_urlsafe(16)}@host','http://host/api','http://host?x=1','http://host#x']:
            self.assertFalse(valid_url(url))


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls=[]
        self.status=200
        self.native=payload()
        self.raw=None
        self.delay=0
        async def parse(req):
            self.calls.append((req.path,await req.json(),dict(req.headers)))
            if self.delay: await asyncio.sleep(self.delay)
            if self.raw is not None: return web.Response(body=self.raw,status=self.status)
            return web.json_response(self.native,status=self.status)
        app=web.Application()
        app.router.add_post('/api/v2/parse',parse)
        self.runner=web.AppRunner(app)
        await self.runner.setup()
        self.site=web.TCPSite(self.runner,'127.0.0.1',0)
        await self.site.start()
        port=self.site._server.sockets[0].getsockname()[1]
        self.session=ClientSession()
        self.test_token=secrets.token_urlsafe(24)
        self.client=KlarClient(self.session,f'http://127.0.0.1:{port}',self.test_token,timeout=0.1)

    async def asyncTearDown(self):
        await self.session.close()
        await self.runner.cleanup()

    async def test_endpoint_metadata_and_no_llm_routes(self):
        req=request(conversation_id='same-session',device_id='device',satellite_id='sat')
        result=await self.client.weather(req,preferred_area='living')
        path,body,headers=self.calls[0]
        self.assertEqual(path,'/api/v2/parse')
        self.assertEqual(body,{'text':req.text,'conversation_id':'same-session','language':'de',
                              'nlu_rag':False,'preferred_area':'living'})
        self.assertEqual(headers['X-Klar-Token'],self.test_token)
        self.assertEqual(result.entity_id,'weather.test')
        self.assertEqual(len(self.calls),1)

    async def test_unavailable_http(self):
        self.status=503
        with self.assertRaises(KlarError): await self.client.weather(request())

    async def test_chat_not_returned_as_weather(self):
        self.native={'schema_version':'2.0','decision':{'type':'chat'}}
        with self.assertRaises(KlarError): await self.client.weather(request())

    async def test_bad_json(self):
        self.raw=b'not json'
        with self.assertRaises(KlarError): await self.client.weather(request())

    async def test_oversized_response(self):
        self.raw=b'x'*131073
        with self.assertRaises(KlarError): await self.client.weather(request())

    async def test_parse_timeout(self):
        self.delay=0.2
        with self.assertRaises(KlarError): await self.client.weather(request())

    async def test_cancellation_propagates(self):
        self.delay=0.2
        task=asyncio.create_task(self.client.weather(request()))
        await asyncio.sleep(0.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task

    async def test_chunked_response_read_to_completion(self):
        original_runner=self.runner
        await original_runner.cleanup()
        async def chunked(req):
            response=web.StreamResponse(status=200,headers={'Content-Type':'application/json'})
            await response.prepare(req)
            data=json.dumps(payload()).encode()
            await response.write(data[:10])
            await asyncio.sleep(0.005)
            await response.write(data[10:])
            await response.write_eof()
            return response
        app=web.Application()
        app.router.add_post('/api/v2/parse',chunked)
        self.runner=web.AppRunner(app)
        await self.runner.setup()
        site=web.TCPSite(self.runner,'127.0.0.1',0)
        await site.start()
        port=site._server.sockets[0].getsockname()[1]
        self.client.url=f'http://127.0.0.1:{port}'
        self.assertEqual((await self.client.weather(request())).entity_id,'weather.test')

    async def test_regional_language_normalized_only_for_parse_api(self):
        for language in ['de-DE','de-AT','DE_de']:
            req=request(language=language)
            await self.client.weather(req)
            self.assertEqual(self.calls[-1][1]['language'],'de')
            self.assertEqual(req.language,language)
        self.assertEqual(len(self.calls),3)

    async def test_invalid_language_does_not_issue_http_request(self):
        with self.assertRaises(KlarError):
            await self.client.weather(request(language='de--DE'))
        self.assertEqual(self.calls,[])
