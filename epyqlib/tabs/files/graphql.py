import asyncio
import json
from typing import Callable

import treq
from twisted.internet import reactor
from twisted.internet.defer import ensureDeferred
from twisted.internet.error import DNSLookupError
from twisted.python.failure import Failure
from twisted.web.iweb import IResponse

from epyqlib.tabs.files.activity_log import Event
from epyqlib.tabs.files.configuration import Configuration, Vars
from epyqlib.tabs.files.websocket_handler import WebSocketHandler
from epyqlib.utils.general import safe_get


class GraphQLException(Exception):
    pass

class InverterNotFoundException(Exception):
    pass


class API:
    ws_handler = WebSocketHandler()
    is_offline = Configuration.get_instance().get(Vars.offline_mode) or False

    server_info = {
        "url": "https://b3oofrroujeutdd4zclqlwedhm.appsync-api.us-west-2.amazonaws.com/graphql",
        "headers": {
          "x-api-key": "da2-77ph5d7dlnghhnlufivpbn3cri"
        }
    }

    list_inverters_query = """
        query {
            listInverters(limit: 200) {
                items {
                    id,
                    serialNumber,
                    notes
                }
                nextToken
            }
        }
    """

    list_inverters = {
        "query": list_inverters_query,
        "variables": {}
    }

    get_inverter_string = """
        query ($inverterId: ID!) { 
            getInverter(id: $inverterId) { 
                createdAt 
                deploymentDate 
                id 
                manufactureDate 
                model { name revision partNumber codes id __typename } 
                notes 
                serialNumber 
                site { 
                    name 
                    id 
                    customer { name id __typename } 
                    __typename 
                } 
                testDate 
                updatedAt 
                updatedBy 
                __typename 
            }
        } 
    """

    def _get_inverter_query(self, inverter_id: str):
        return {
            "query": self.get_inverter_string,
            "variables": {
                "inverterId": inverter_id
            }
        }

    get_association_str = """
        query ($serialNumber: String) {
            getInverterAssociations(serialNumber: $serialNumber) {
                items {
                    id
                    customer { name }
                    file {id, description, filename, hash, notes, type, uploadPath, version}
                    model {name}
                    inverter {id, serialNumber}
                    site {name}
                    
                    # updatedAt
                }
            }
        }
    """

    def _get_association_query(self, serial_number: str):
        return {
            "query": self.get_association_str,
            "variables": {
                "serialNumber": serial_number
            }
        }

    _ping_query = """
        query {
            __schema {
                 types {
                     name
                 }
            }
        }
    """

    def _get_ping_query(self):
        return {
            "query": self._ping_query,
            "variables": {}
        }



    #   createActivity(inverterId: String!, timestamp: String!, type: String!, customerId: String, siteId: String, actionJson: String!): Activity!
    _create_activity = """
        mutation Name (
            $inverterId: String!,
            $timestamp: String!,
            $type: String!,
            $actionJson: String!
        ){
            createActivity(
                inverterId: $inverterId,
                timestamp: $timestamp,
                type: $type,
                actionJson: $actionJson
            ) {
                  inverterId
                  customerId
                  siteId
                  timestamp
                  actionJson
                  type
                  createdBy
            }
        }
    """

    def _get_create_activity_mutation(self, inverter_id: str, timestamp: str, type: str, action_json: str):
        return {
            "query": self._create_activity,
            "variables": {
                "actionJson": action_json,
                "inverterId": inverter_id,
                "timestamp": timestamp,
                "type": type
            }
        }

    async def _make_request(self, body):
        url = self.server_info["url"]
        headers = self.server_info["headers"]
        response: IResponse = await treq.post(url, headers=headers, json=body)
        if response.code >= 400:
            raise GraphQLException(f"{response.code} {response.phrase.decode('ascii')}")

        # content = await treq.content(response)
        body = await treq.json_content(response)

        if (body.get('data') is None and body.get('errors') is not None):
            raise GraphQLException(body['errors'])

        return body


    async def fetch_inverter_list(self):
        response = await self._make_request(self.list_inverters)

        return response['data']['listInverters']['items']

    async def get_inverter_test(self):
        return await self.get_inverter("d2ea61cf-50f1-4ece-9caa-8b5fd250036d")

    async def get_inverter(self, inverter_id: str):
        response = await self._make_request(self._get_inverter_query(inverter_id))
        return response['data']['getInverter']

    async def get_associations(self, serial_number: str):
        """
        :raises InverterNotFoundException
        """
        response = await self._make_request(self._get_association_query(serial_number))
        message = safe_get(response, ['errors', 0, 'message']) or ''
        if ('Unable to find inverter' in message):
            raise InverterNotFoundException(message)

        return response['data']['getInverterAssociations']['items']

    async def create_activity(self, event: Event):
        details_json = json.dumps(event.details)
        request_body = self._get_create_activity_mutation(event.inverter_id, event.timestamp, event.type, details_json)
        print("[Graphql] Sending create activity request: " + json.dumps(request_body))
        response = await self._make_request(request_body)
        print(json.dumps(response))

    async def test_connection(self):
        try:
            response = await self._make_request(self._get_ping_query())
            print("[Graphql] Connection test succeeded.")
        except DNSLookupError:
            print("[Graphql] Connection test failed. Setting offline mode to true.")
            self.is_offline = True

    def awai(self, coroutine):
        # Or `async.run(coroutine)`
        return asyncio.get_event_loop().run_until_complete(coroutine)

    def run(self, coroutine):
        from twisted.internet.defer import ensureDeferred
        deferred = ensureDeferred(coroutine)
        deferred.addCallback(succ)
        deferred.addErrback(err)
        return deferred


    async def subscribe(self, message_handler: Callable[[str, dict], None]):
        gql = """subscription {
                    created: fileCreated { id }
                    updated: fileUpdated { id }
                    deleted: fileDeleted { id }
                }"""

        query = {
            "query": gql,
            "variables": {}
        }

        response = await self._make_request(query)
        mqttInfo = response['extensions']['subscription']['mqttConnections'][0]
        topics = response['extensions']['subscription']['newSubscriptions']
        client_id = mqttInfo['client']
        url = mqttInfo['url']
        self.ws_handler.connect(url, client_id, topics, message_handler)

    def is_subscribed(self):
        return self.ws_handler.is_subscribed()

    async def unsubscribe(self):
        if self.ws_handler.is_subscribed():
            self.ws_handler.disconnect()


def main(reactor):
    from twisted.internet.defer import ensureDeferred

    api = API()
    deferred = ensureDeferred(api.get_associations("TestInv"))
    deferred.addCallback(succ)
    deferred.addErrback(err)
    return deferred

def succ(body):
    print("SUCCESS")
    print(body)

def err(error: Failure):
    print("ERROR ENCOUNTERED")
    print(error.type)
    print(error.value)
    print(error.getBriefTraceback())
    reactor.stop()


if __name__ == "__main__":
    # from twisted.internet.task import react
    # react(main)

    api = API()
    d = ensureDeferred(api.subscribe())
    d.addCallback(succ)
    d.addErrback(err)
    # ensureDeferred(api.test_connection())
    reactor.run()