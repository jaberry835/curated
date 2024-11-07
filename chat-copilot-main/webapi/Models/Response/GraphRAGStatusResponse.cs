
// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace CopilotChat.WebApi.Models.Response;

public class GraphRAGStatusResponse
{
    [JsonPropertyName("id")]
    public string Id { get; set; }

    [JsonPropertyName("query")]
    public string Query { get; set; }

    [JsonPropertyName("status")]
    public string Status { get; set; }

    [JsonPropertyName("result")]
    public string Result { get; set; }
}
