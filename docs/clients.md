# Client Examples

All clients can call the same `/api/v1/dispatch` endpoint.

## Java

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class DesktopMcpClient {
  public static void main(String[] args) throws Exception {
    var body = """
      {
        "request_id": "java-demo-1",
        "action": "list_projects",
        "params": {}
      }
      """;

    var request = HttpRequest.newBuilder()
        .uri(URI.create("http://127.0.0.1:8765/api/v1/dispatch"))
        .header("Content-Type", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(body))
        .build();

    var response = HttpClient.newHttpClient()
        .send(request, HttpResponse.BodyHandlers.ofString());

    System.out.println(response.body());
  }
}
```

## Python

```python
import requests

payload = {
    "request_id": "python-demo-1",
    "action": "list_projects",
    "params": {},
}

response = requests.post(
    "http://127.0.0.1:8765/api/v1/dispatch",
    json=payload,
    timeout=10,
)
print(response.json())
```

## Go

```go
package main

import (
	"bytes"
	"fmt"
	"io"
	"net/http"
)

func main() {
	body := []byte(`{
	  "request_id": "go-demo-1",
	  "action": "list_projects",
	  "params": {}
	}`)

	resp, err := http.Post(
		"http://127.0.0.1:8765/api/v1/dispatch",
		"application/json",
		bytes.NewReader(body),
	)
	if err != nil {
		panic(err)
	}
	defer resp.Body.Close()

	data, _ := io.ReadAll(resp.Body)
	fmt.Println(string(data))
}
```

## Recommended Client Behavior

- Use `/api/v1/actions` at startup if the client wants capability discovery.
- Send a `request_id` for log correlation.
- Speak `spoken_message` on success.
- Speak `error_spoken_message` on failure.
- Use pending actions for medium-risk operations that need confirmation.
