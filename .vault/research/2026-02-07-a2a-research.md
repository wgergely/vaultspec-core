---
tags:
  - "#research"
  - "#protocol"
date: "2026-02-07"
---
# A2A (Agent-to-Agent) Protocol -- Technical Reference

**Date:** 2026-02-07
**Source:** Research agent -- A2A protocol deep dive
**Scope:** Full protobuf spec, SDK APIs, code examples, task lifecycle

---

## Protocol Overview

A2A is an open standard created by Google (April 2025), donated to Linux Foundation (June 2025). Enables communication between AI agents built on diverse frameworks. Transport: HTTP(S), JSON-RPC 2.0, SSE, gRPC.

**Latest version**: 0.3.x. 150+ supporting organizations.

### Core Principles

- Built on HTTP, JSON-RPC, SSE -- no reinvention
- Enterprise-ready: auth, security, tracing
- Asynchronous: native long-running task support
- Opaque execution: agents collaborate without exposing internals

### Protocol Stack

| Protocol | Focus |
|---|---|
| **A2A** | Agent-to-agent collaboration (horizontal) |
| **MCP** | Agent-to-tool/resource connection (vertical) |
| **ACP** | Editor-to-agent communication (client-agent) |

---

## Core Actors

```
User  --->  A2A Client (Client Agent)  --->  A2A Server (Remote Agent)
```

- **User**: Human or automated service initiating requests
- **A2A Client**: Application/agent acting on behalf of the user
- **A2A Server**: AI agent exposing HTTP endpoints; operates as opaque black-box

---

## Service Definition (11 RPCs)

```protobuf
service A2AService {
  rpc SendMessage(SendMessageRequest) returns (SendMessageResponse);       // POST /message:send
  rpc SendStreamingMessage(SendMessageRequest) returns (stream StreamResponse); // POST /message:stream
  rpc GetTask(GetTaskRequest) returns (Task);                              // GET /tasks/{id}
  rpc ListTasks(ListTasksRequest) returns (ListTasksResponse);             // GET /tasks
  rpc CancelTask(CancelTaskRequest) returns (Task);                        // POST /tasks/{id}:cancel
  rpc SubscribeToTask(SubscribeToTaskRequest) returns (stream StreamResponse);
  rpc CreateTaskPushNotificationConfig(...) returns (TaskPushNotificationConfig);
  rpc GetTaskPushNotificationConfig(...)    returns (TaskPushNotificationConfig);
  rpc ListTaskPushNotificationConfig(...)   returns (ListTaskPushNotificationConfigResponse);
  rpc DeleteTaskPushNotificationConfig(...) returns (google.protobuf.Empty);
  rpc GetExtendedAgentCard(GetExtendedAgentCardRequest) returns (AgentCard);
}
```

---

## Task State Machine (9 States)

```
submitted --> working --> input_required --> completed
                    \                   /
                     --> failed / canceled / rejected / auth_required
```

| State | Category | Description |
|---|---|---|
| `submitted` | Active | Task created, acknowledged |
| `working` | Active | Being processed |
| `input_required` | Interrupted | Needs more info from client |
| `auth_required` | Interrupted | Authentication needed |
| `completed` | Terminal | Finished successfully |
| `failed` | Terminal | Done but failed |
| `canceled` | Terminal | Canceled before finishing |
| `rejected` | Terminal | Agent declined the task |

**Immutability rule**: Once terminal, a task cannot restart. New work creates a new task in the same `contextId`.

---

## Core Data Types

### Task

```protobuf
message Task {
  string id = 1;                       // UUID, server-generated
  string context_id = 2;               // Groups related interactions
  TaskStatus status = 3;               // Current state + message
  repeated Artifact artifacts = 4;     // Output artifacts
  repeated Message history = 5;        // Interaction history
  google.protobuf.Struct metadata = 6;
}

message TaskStatus {
  TaskState state = 1;
  Message message = 2;
  google.protobuf.Timestamp timestamp = 3;
}
```

### Message

```protobuf
message Message {
  string message_id = 1;
  string context_id = 2;
  string task_id = 3;
  Role role = 4;                       // USER or AGENT
  repeated Part parts = 5;
  google.protobuf.Struct metadata = 6;
  repeated string extensions = 7;
  repeated string reference_task_ids = 8;
}
```

### Part (Content Container)

```protobuf
message Part {
  oneof content {
    string text = 1;
    bytes raw = 2;
    string url = 3;
    google.protobuf.Value data = 4;    // Structured JSON
  }
  google.protobuf.Struct metadata = 5;
  string filename = 6;
  string media_type = 7;
}
```

### Artifact (Task Output)

```protobuf
message Artifact {
  string artifact_id = 1;
  string name = 3;
  string description = 4;
  repeated Part parts = 5;
  google.protobuf.Struct metadata = 6;
  repeated string extensions = 7;
}
```

### Streaming Event Types

```protobuf
message TaskStatusUpdateEvent {
  string task_id = 1;
  string context_id = 2;
  TaskStatus status = 3;
  google.protobuf.Struct metadata = 5;
}

message TaskArtifactUpdateEvent {
  string task_id = 1;
  string context_id = 2;
  Artifact artifact = 3;
  bool append = 4;       // Append to previous artifact with same ID
  bool last_chunk = 5;   // Final chunk of this artifact
  google.protobuf.Struct metadata = 6;
}

message StreamResponse {
  oneof payload {
    Task task = 1;
    Message message = 2;
    TaskStatusUpdateEvent status_update = 3;
    TaskArtifactUpdateEvent artifact_update = 4;
  }
}

message SendMessageResponse {
  oneof payload {
    Task task = 1;
    Message message = 2;
  }
}
```

---

## Agent Card (Discovery)

Served at `/.well-known/agent-card.json`:

```protobuf
message AgentCard {
  string name = 1;
  string description = 2;
  repeated AgentInterface supported_interfaces = 19;
  AgentProvider provider = 4;
  string version = 5;
  optional string documentation_url = 6;
  AgentCapabilities capabilities = 7;
  map<string, SecurityScheme> security_schemes = 8;
  repeated SecurityRequirement security_requirements = 13;
  repeated string default_input_modes = 10;
  repeated string default_output_modes = 11;
  repeated AgentSkill skills = 12;
  repeated AgentCardSignature signatures = 17;
  optional string icon_url = 18;
}

message AgentInterface {
  string url = 1;              // "https://api.example.com/a2a/v1"
  string protocol_binding = 2; // "JSONRPC", "GRPC", "HTTP+JSON"
  string tenant = 3;
  string protocol_version = 4; // "0.3"
}

message AgentCapabilities {
  optional bool streaming = 1;
  optional bool push_notifications = 2;
  repeated AgentExtension extensions = 3;
  optional bool extended_agent_card = 5;
}

message AgentSkill {
  string id = 1;
  string name = 2;
  string description = 3;
  repeated string tags = 4;
  repeated string examples = 5;
  repeated string input_modes = 6;
  repeated string output_modes = 7;
  repeated SecurityRequirement security_requirements = 8;
}
```

### Agent Card JSON Example

```json
{
  "name": "Currency Agent",
  "description": "Helps with exchange rates",
  "url": "http://localhost:10000/",
  "version": "1.0.0",
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"],
  "capabilities": { "streaming": true, "pushNotifications": true },
  "skills": [{
    "id": "convert_currency",
    "name": "Currency Exchange",
    "description": "Exchange rate lookups",
    "tags": ["currency"],
    "examples": ["What is USD to EUR?"]
  }],
  "supportedInterfaces": [{
    "url": "http://localhost:10000/",
    "protocolBinding": "JSONRPC",
    "protocolVersion": "0.3"
  }]
}
```

### Discovery Methods

- **Well-Known URI** (recommended): `GET https://{domain}/.well-known/agent-card.json`
- **Curated Registries**: Central repositories queried by skill/tags/capabilities
- **Direct Configuration**: Hardcoded URLs for tightly coupled systems
- **Extended Agent Card**: Authenticated endpoint at `GET /extendedAgentCard`

### Security Schemes

Supports: API keys, HTTP auth (Bearer/Basic), OAuth 2.0 (authorization code, client credentials, device code), OpenID Connect, mTLS.

---

## Interaction Mechanisms

### Request/Response (Polling)

`POST /message:send` -> returns `Task` or `Message`. Poll with `GET /tasks/{id}`.

### Streaming (SSE)

`POST /message:stream` -> `Content-Type: text/event-stream`. Events: `Task`, `TaskStatusUpdateEvent`, `TaskArtifactUpdateEvent`. Resubscribe via `GET /tasks/{id}:subscribe`.

### Push Notifications

Webhook-based. Server POSTs `StreamResponse` to client URL. Security: JWT + JWKS, HMAC, mTLS.

---

## Agent Response Patterns

- **Message-only**: Stateless, wrapping LLM calls
- **Task-generating**: Always returns `Task` objects
- **Hybrid**: `Message` for negotiation, then `Task` for tracked work

---

## Request/Response Types

```protobuf
message SendMessageRequest {
  string tenant = 4;
  Message message = 1;
  SendMessageConfiguration configuration = 2;
  google.protobuf.Struct metadata = 3;
}

message SendMessageConfiguration {
  repeated string accepted_output_modes = 1;
  PushNotificationConfig push_notification_config = 2;
  optional int32 history_length = 3;
  bool blocking = 4;
}

message GetTaskRequest {
  string tenant = 3;
  string id = 1;
  optional int32 history_length = 2;
}

message ListTasksRequest {
  string tenant = 9;
  string context_id = 1;
  TaskState status = 2;
  optional int32 page_size = 3;      // 1-100, default 50
  string page_token = 4;
  optional int32 history_length = 5;
  google.protobuf.Timestamp status_timestamp_after = 6;
  optional bool include_artifacts = 7;
}

message PushNotificationConfig {
  string id = 1;
  string url = 2;               // Webhook URL
  string token = 3;             // Session token
  AuthenticationInfo authentication = 4;
}
```

---

## Python SDK (`a2a-sdk`)

**Install**: `pip install a2a-sdk` (v0.3.22, Python >=3.10)
**Extras**: encryption, grpc, http-server, mysql, postgres, signing, sql, sqlite, telemetry

### Core Classes

**AgentExecutor** (implement this):

```python
class AgentExecutor(ABC):
    @abstractmethod
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None: ...
    @abstractmethod
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None: ...
```

**RequestContext**: Provides `message`, `current_task`, `task_id`, `context_id`, `configuration`, `metadata`, `related_tasks`, `get_user_input()`.

**EventQueue**: `enqueue_event()`, `dequeue_event()`, `tap()`, `close()`. Events: `Message`, `Task`, `TaskStatusUpdateEvent`, `TaskArtifactUpdateEvent`.

**TaskUpdater**: `update_status()`, `add_artifact()`, `complete()`.

**Client** (abstract):

```python
class Client(ABC):
    async def send_message(self, request, **kwargs) -> AsyncIterator[ClientEvent | Message]: ...
    async def get_task(self, request, **kwargs) -> Task: ...
    async def cancel_task(self, request, **kwargs) -> Task: ...
    async def set_task_callback(self, request, **kwargs) -> TaskPushNotificationConfig: ...
    async def get_task_callback(self, request, **kwargs) -> TaskPushNotificationConfig: ...
    async def resubscribe(self, request, **kwargs) -> AsyncIterator[ClientEvent]: ...
    async def get_card(self, **kwargs) -> AgentCard: ...
```

### Server Setup

```python
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

handler = DefaultRequestHandler(
    agent_executor=MyExecutor(),
    task_store=InMemoryTaskStore(),
)
server = A2AStarletteApplication(agent_card=card, http_handler=handler)
uvicorn.run(server.build(), host='0.0.0.0', port=9999)
```

### Client Usage

```python
from a2a.client import A2ACardResolver, A2AClient

resolver = A2ACardResolver(httpx_client=client, base_url=url)
card = await resolver.get_agent_card()
a2a_client = A2AClient(httpx_client=client, agent_card=card)
response = await a2a_client.send_message(request)
```

---

## Complete Working Examples

### HelloWorld Agent (Minimal)

**Server:**

```python
import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from a2a.utils import new_agent_text_message

class HelloWorldExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        await event_queue.enqueue_event(new_agent_text_message('Hello World'))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise Exception('cancel not supported')

agent_card = AgentCard(
    name='Hello World Agent',
    description='Just a hello world agent',
    url='http://localhost:9999/',
    version='1.0.0',
    default_input_modes=['text'],
    default_output_modes=['text'],
    capabilities=AgentCapabilities(streaming=True),
    skills=[AgentSkill(
        id='hello_world', name='Returns hello world',
        description='just returns hello world',
        tags=['hello world'], examples=['hi', 'hello world'],
    )],
)

handler = DefaultRequestHandler(
    agent_executor=HelloWorldExecutor(),
    task_store=InMemoryTaskStore(),
)
server = A2AStarletteApplication(agent_card=agent_card, http_handler=handler)
uvicorn.run(server.build(), host='0.0.0.0', port=9999)
```

**Client:**

```python
import httpx
from uuid import uuid4
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import MessageSendParams, SendMessageRequest

async def main():
    async with httpx.AsyncClient() as httpx_client:
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url='http://localhost:9999')
        agent_card = await resolver.get_agent_card()
        client = A2AClient(httpx_client=httpx_client, agent_card=agent_card)

        payload = {
            'message': {
                'role': 'user',
                'parts': [{'kind': 'text', 'text': 'hello'}],
                'messageId': uuid4().hex,
            },
        }
        request = SendMessageRequest(id=str(uuid4()), params=MessageSendParams(**payload))
        response = await client.send_message(request)
        print(response.model_dump(mode='json', exclude_none=True))
```

### Currency Agent (Streaming + Multi-turn + Task State)

**Executor with TaskUpdater:**

```python
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TaskState, TextPart
from a2a.utils import new_agent_text_message, new_task

class CurrencyAgentExecutor(AgentExecutor):
    def __init__(self):
        self.agent = CurrencyAgent()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        query = context.get_user_input()
        task = context.current_task
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.context_id)

        async for item in self.agent.stream(query, task.context_id):
            if not item['is_task_complete'] and not item['require_user_input']:
                await updater.update_status(
                    TaskState.working,
                    new_agent_text_message(item['content'], task.context_id, task.id),
                )
            elif item['require_user_input']:
                await updater.update_status(
                    TaskState.input_required,
                    new_agent_text_message(item['content'], task.context_id, task.id),
                    final=True,
                )
                break
            else:
                await updater.add_artifact(
                    [Part(root=TextPart(text=item['content']))],
                    name='conversion_result',
                )
                await updater.complete()
                break

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise Exception('cancel not supported')
```

**Server with push notifications:**

```python
import httpx
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.push_notification import InMemoryPushNotificationConfigStore, BasePushNotificationSender

httpx_client = httpx.AsyncClient()
push_config_store = InMemoryPushNotificationConfigStore()
push_sender = BasePushNotificationSender(
    httpx_client=httpx_client, config_store=push_config_store
)
handler = DefaultRequestHandler(
    agent_executor=CurrencyAgentExecutor(),
    task_store=InMemoryTaskStore(),
    push_config_store=push_config_store,
    push_sender=push_sender,
)
server = A2AStarletteApplication(agent_card=agent_card, http_handler=handler)
uvicorn.run(server.build(), host='localhost', port=10000)
```

---

## Multi-turn Flow

```
Turn 1: Client sends ambiguous query
  POST /message:send  "How much is 100 USD?"
  -> Server returns Task { state: "input_required", message: "To which currency?" }

Turn 2: Client responds with same taskId + contextId
  POST /message:send  { taskId: "task-1", contextId: "ctx-1", message: "in GBP" }
  -> Server returns Task { state: "completed", artifacts: [{ text: "79.23 GBP" }] }
```

### Parallel Follow-ups

Multiple concurrent tasks within the same context:

- Task 1: Book a flight to Helsinki
- Task 2: Based on Task 1 -> Book a hotel (via `referenceTaskIds`)
- Task 3: Based on Task 1 -> Book a snowmobile activity
- Task 4: Based on Task 2 -> Add spa reservation

---

## Streaming Sequence

```
Client                              Server
  |-- POST /message:stream -------->|
  |<-- SSE: Task (submitted) ------|
  |<-- SSE: StatusUpdate (working) |
  |<-- SSE: ArtifactUpdate --------|
  |<-- SSE: StatusUpdate (complete)|
  |<-- Stream closed ---------------|
```

---

## Request Lifecycle (with Auth)

```
Client                        A2A Server               Auth Server
  |                                |                        |
  |-- GET /.well-known/agent-card->|                        |
  |<-- Returns Agent Card --------|                        |
  |                                |                        |
  |-- Parse securitySchemes ------>|                        |
  |-- Request token -------------->|--------------------->  |
  |<-- Returns JWT <--------------|<--------------------- |
  |                                |                        |
  |-- POST /message:send -------->|                        |
  |   (with JWT)                   |                        |
  |<-- Returns Task Response -----|                        |
```

---

## Sources

- <https://github.com/a2aproject/A2A>
- <https://a2a-protocol.org/latest/specification/>
- <https://a2a-protocol.org/latest/definitions/>
- <https://a2a-protocol.org/dev/topics/life-of-a-task/>
- <https://a2a-protocol.org/latest/topics/key-concepts/>
- <https://a2a-protocol.org/latest/topics/streaming-and-async/>
- <https://a2a-protocol.org/latest/topics/agent-discovery/>
- <https://a2a-protocol.org/latest/topics/a2a-and-mcp/>
- <https://a2a-protocol.org/latest/sdk/python/api/>
- <https://github.com/a2aproject/a2a-python>
- <https://pypi.org/project/a2a-sdk/>
- <https://github.com/a2aproject/a2a-samples>
- <https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/>
- <https://cloud.google.com/blog/products/ai-machine-learning/agent2agent-protocol-is-getting-an-upgrade>
- <https://www.linuxfoundation.org/press/linux-foundation-launches-the-agent2agent-protocol-project>
- <https://www.ibm.com/think/topics/agent2agent-protocol>
- <https://a2aprotocol.ai/blog/2025-full-guide-a2a-protocol>
- <https://codelabs.developers.google.com/intro-a2a-purchasing-concierge>
- <https://semgrep.dev/blog/2025/a-security-engineers-guide-to-the-a2a-protocol/>
- <https://heidloff.net/article/mcp-acp-a2a-agent-protocols/>
- <https://auth0.com/blog/mcp-vs-a2a/>
- <https://akka.io/blog/mcp-a2a-acp-what-does-it-all-mean>
- <https://workos.com/guide/understanding-mcp-acp-a2a>
- <https://huggingface.co/blog/1bo/a2a-protocol-explained>
- <https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-a2a-protocol-contract.html>
- <https://arxiv.org/html/2505.02279v1>
