using Microsoft.AspNetCore.Mvc;
using MCPServer.Models;
using MCPServer.Services.Azure;
using MCPServer.Services;
using System.Text.Json;
using System.Text;

namespace MCPServer.Controllers;

[ApiController]
[Route("api/[controller]")]
public class ChatController : ControllerBase
{
    private readonly IChatHistoryService _chatHistoryService;
    private readonly ILogger<ChatController> _logger;
    private readonly IConfiguration _configuration;
    private readonly IToolService _toolService;

    public ChatController(
        IChatHistoryService chatHistoryService,
        ILogger<ChatController> logger,
        IConfiguration configuration,
        IToolService toolService)
    {
        _chatHistoryService = chatHistoryService;
        _logger = logger;
        _configuration = configuration;
        _toolService = toolService;
    }

    [HttpPost("message")]
    public async Task<ActionResult<string>> SaveMessage([FromBody] ChatMessage message)
    {
        try
        {
            _logger.LogInformation("Saving message for session {SessionId}", message.SessionId);
            
            var messageId = await _chatHistoryService.SaveMessageAsync(message);
            
            return Ok(new { messageId });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error saving message");
            return StatusCode(500, new { error = "Failed to save message" });
        }
    }

    [HttpGet("history")]
    public async Task<ActionResult<ChatHistoryResponse>> GetChatHistory(
        [FromQuery] string userId,
        [FromQuery] string sessionId,
        [FromQuery] int pageSize = 50,
        [FromQuery] string? continuationToken = null)
    {
        try
        {
            _logger.LogInformation("Getting chat history for session {SessionId}", sessionId);
            
            var request = new ChatHistoryRequest
            {
                UserId = userId,
                SessionId = sessionId,
                PageSize = pageSize,
                ContinuationToken = continuationToken
            };

            var response = await _chatHistoryService.GetChatHistoryAsync(request);
            
            return Ok(response);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error retrieving chat history for session {SessionId}", sessionId);
            return StatusCode(500, new { error = "Failed to retrieve chat history" });
        }
    }

    [HttpPost("session")]
    public async Task<ActionResult<string>> CreateSession([FromBody] CreateSessionRequest request)
    {
        try
        {
            _logger.LogInformation("Creating session for user {UserId}", request.UserId);
            
            var sessionId = await _chatHistoryService.CreateSessionAsync(request.UserId, request.Title);
            
            return Ok(new { sessionId });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error creating session for user {UserId}", request.UserId);
            return StatusCode(500, new { error = "Failed to create session" });
        }
    }

    [HttpGet("sessions")]
    public async Task<ActionResult<SessionListResponse>> GetSessions(
        [FromQuery] string userId,
        [FromQuery] int pageSize = 20,
        [FromQuery] string? continuationToken = null,
        [FromQuery] bool includeArchived = false)
    {
        try
        {
            _logger.LogInformation("Getting sessions for user {UserId}", userId);
            
            var request = new SessionListRequest
            {
                UserId = userId,
                PageSize = pageSize,
                ContinuationToken = continuationToken,
                IncludeArchived = includeArchived
            };

            var response = await _chatHistoryService.GetUserSessionsAsync(request);
            
            return Ok(response);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error retrieving sessions for user {UserId}", userId);
            return StatusCode(500, new { error = "Failed to retrieve sessions" });
        }
    }    [HttpPut("session/{sessionId}")]
    public async Task<ActionResult> UpdateSession(string sessionId, [FromBody] ChatSession session)
    {
        try
        {
            if (sessionId != session.Id)
            {
                return BadRequest("Session ID mismatch");
            }

            _logger.LogInformation("Updating session title: {SessionId} -> {Title}", sessionId, session.Title);
            
            // Only update the title to avoid overwriting the Documents array
            await _chatHistoryService.UpdateSessionTitleAsync(session.UserId, sessionId, session.Title);
            
            return Ok();
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error updating session {SessionId}", sessionId);
            return StatusCode(500, new { error = "Failed to update session" });
        }
    }

    [HttpDelete("session/{sessionId}")]
    public async Task<ActionResult> DeleteSession(string sessionId, [FromQuery] string userId)
    {
        try
        {
            _logger.LogInformation("Deleting session {SessionId}", sessionId);
            
            await _chatHistoryService.DeleteSessionAsync(userId, sessionId);
            
            return Ok();
        }        catch (Exception ex)
        {
            _logger.LogError(ex, "Error deleting session {SessionId}", sessionId);
            return StatusCode(500, new { error = "Failed to delete session" });
        }
    }

    [HttpPost("completions")]
    public async Task<ActionResult> GetChatCompletion([FromBody] ChatCompletionRequest request)
    {
        try
        {
            _logger.LogInformation("Processing chat completion for session {SessionId}", request.SessionId);

            // Get Azure OpenAI configuration
            var endpoint = _configuration["AzureOpenAI:Endpoint"];
            var apiKey = _configuration["AzureOpenAI:ApiKey"];
            var deploymentName = _configuration["AzureOpenAI:DeploymentName"] ?? "gpt-4o";

            if (string.IsNullOrEmpty(endpoint) || string.IsNullOrEmpty(apiKey))
            {
                _logger.LogError("Azure OpenAI configuration is missing");
                return StatusCode(500, new { error = "Azure OpenAI configuration is missing" });
            }            // 1. Get available MCP tools (following the pattern from the article)
            var mcpTools = await _toolService.GetAvailableToolsAsync();
            var azureTools = ConvertMcpToolsToAzureFormat(mcpTools);

            _logger.LogInformation("Available MCP tools: {ToolCount}", mcpTools.Count());
            foreach (var tool in mcpTools)
            {
                _logger.LogInformation("Tool: {ToolName} - {ToolDescription}", tool.Name, tool.Description);
            }

            // 2. Build messages for Azure OpenAI
            var azureMessages = new List<object>();
            
            // Add system prompt if available
            var systemPrompt = _configuration["SystemPrompt"];
            if (!string.IsNullOrEmpty(systemPrompt))
            {
                azureMessages.Add(new { role = "system", content = systemPrompt });
            }

            // Add conversation messages
            foreach (var chatMessage in request.Messages)
            {
                azureMessages.Add(new { role = chatMessage.Role, content = chatMessage.Content });
            }

            // 3. Make initial call to Azure OpenAI with tools
            var azureRequest = new
            {
                messages = azureMessages,
                max_tokens = 4000,
                temperature = 0.7,
                stream = false,
                tools = azureTools.Any() ? azureTools : null,
                tool_choice = azureTools.Any() ? "auto" : null
            };            using var httpClient = new HttpClient();
            httpClient.Timeout = TimeSpan.FromMinutes(2); // Set 2-minute timeout
            httpClient.DefaultRequestHeaders.Add("api-key", apiKey);

            var requestJson = JsonSerializer.Serialize(azureRequest);
            var content = new StringContent(requestJson, Encoding.UTF8, "application/json");

            var apiUrl = $"{endpoint.TrimEnd('/')}/openai/deployments/{deploymentName}/chat/completions?api-version=2024-02-15-preview";
            var response = await httpClient.PostAsync(apiUrl, content);

            if (!response.IsSuccessStatusCode)
            {
                var errorContent = await response.Content.ReadAsStringAsync();
                _logger.LogError("Azure OpenAI API error: {StatusCode} - {Content}", response.StatusCode, errorContent);
                return StatusCode(500, new { error = "Failed to get completion from Azure OpenAI" });
            }            var responseJson = await response.Content.ReadAsStringAsync();
            var azureResponse = JsonSerializer.Deserialize<JsonElement>(responseJson);

            _logger.LogInformation("Azure OpenAI response received, checking for tool calls...");

            // 4. Check for tool calls and execute them (following MCP pattern)
            var choice = azureResponse.GetProperty("choices")[0];
            var message = choice.GetProperty("message");
            
            _logger.LogInformation("Response message role: {Role}", message.GetProperty("role").GetString());
            
            if (message.TryGetProperty("content", out var contentElement))
            {
                _logger.LogInformation("Response content: {Content}", contentElement.GetString());
            }
              if (message.TryGetProperty("tool_calls", out var toolCallsElement) && 
                toolCallsElement.ValueKind == JsonValueKind.Array && 
                toolCallsElement.GetArrayLength() > 0)
            {
                var messages = azureMessages.ToList();
                var currentResponse = azureResponse;
                var iterationCount = 0;
                const int maxIterations = 10; // Safety limit to prevent infinite loops
                
                // Continue looping until no more tool calls are requested
                while (true)
                {
                    iterationCount++;
                    _logger.LogInformation("Tool execution iteration {Iteration}", iterationCount);
                    
                    if (iterationCount > maxIterations)
                    {
                        _logger.LogWarning("Reached maximum tool call iterations ({Max}), stopping", maxIterations);
                        break;
                    }
                    
                    // Get current tool calls
                    var currentChoice = currentResponse.GetProperty("choices")[0];
                    var currentMessage = currentChoice.GetProperty("message");
                    
                    if (!currentMessage.TryGetProperty("tool_calls", out var currentToolCalls) || 
                        currentToolCalls.ValueKind != JsonValueKind.Array || 
                        currentToolCalls.GetArrayLength() == 0)
                    {
                        _logger.LogInformation("No more tool calls found, ending iteration");
                        break;
                    }
                    
                    _logger.LogInformation("Processing {ToolCallCount} tool calls in iteration {Iteration}", 
                        currentToolCalls.GetArrayLength(), iterationCount);
                    
                    // Execute all tool calls in this iteration
                    var toolResults = new List<object>();
                    
                    foreach (var toolCall in currentToolCalls.EnumerateArray())
                    {
                        var toolName = toolCall.GetProperty("function").GetProperty("name").GetString();
                        var toolArgs = toolCall.GetProperty("function").GetProperty("arguments").GetString();
                        var toolCallId = toolCall.GetProperty("id").GetString();

                        _logger.LogInformation("Executing tool: {ToolName}", toolName);

                        var toolRequest = new McpToolCallRequest
                        {
                            Name = toolName ?? "",
                            Arguments = JsonSerializer.Deserialize<Dictionary<string, object>>(toolArgs ?? "{}") ?? new Dictionary<string, object>()
                        };

                        var toolResult = await _toolService.ExecuteToolAsync(toolRequest);
                        var resultText = toolResult?.Content?.FirstOrDefault()?.Text ?? "Tool executed";

                        _logger.LogInformation("Tool {ToolName} result: {Result}", toolName, resultText);

                        toolResults.Add(new
                        {
                            tool_call_id = toolCallId,
                            role = "tool",
                            name = toolName,
                            content = resultText
                        });
                    }
                    
                    // Add assistant message with tool calls and tool results to conversation
                    messages.Add(new { role = "assistant", content = (string?)null, tool_calls = currentToolCalls });
                    messages.AddRange(toolResults);
                    
                    // Make next call to see if more tools are needed
                    var nextRequest = new
                    {
                        messages = messages,
                        max_tokens = 4000,
                        temperature = 0.7,
                        stream = false,
                        tools = azureTools.Any() ? azureTools : null,
                        tool_choice = "auto"
                    };

                    var nextJson = JsonSerializer.Serialize(nextRequest);
                    var nextContent = new StringContent(nextJson, Encoding.UTF8, "application/json");
                    var nextResponse = await httpClient.PostAsync(apiUrl, nextContent);

                    if (!nextResponse.IsSuccessStatusCode)
                    {
                        var errorContent = await nextResponse.Content.ReadAsStringAsync();
                        _logger.LogError("Azure OpenAI API error in iteration {Iteration}: {StatusCode} - {Content}", 
                            iterationCount, nextResponse.StatusCode, errorContent);
                        break;
                    }

                    var nextResponseJson = await nextResponse.Content.ReadAsStringAsync();
                    currentResponse = JsonSerializer.Deserialize<JsonElement>(nextResponseJson);
                    
                    _logger.LogInformation("Iteration {Iteration} completed, checking for more tool calls", iterationCount);                }
                
                // Return the final response
                _logger.LogInformation("Tool execution completed after {Iterations} iterations", iterationCount);
                azureResponse = currentResponse;
            }
            else
            {
                _logger.LogInformation("No tool calls found in initial response. LLM provided direct answer without using tools.");
                _logger.LogInformation("Available tools were: {ToolNames}", string.Join(", ", mcpTools.Select(t => t.Name)));
            }

            // 6. Extract final response and save
            var finalChoice = azureResponse.GetProperty("choices")[0];
            var finalMessage = finalChoice.GetProperty("message");
            
            var assistantMessage = finalMessage.TryGetProperty("content", out var contentProp) && 
                                 contentProp.ValueKind != JsonValueKind.Null 
                ? contentProp.GetString() 
                : null;

            // If we still don't have content, provide a default response
            if (string.IsNullOrEmpty(assistantMessage))
            {
                assistantMessage = "I've executed the requested tools but didn't generate a text response. Please check the tool execution results.";
                _logger.LogWarning("No content in final response, using default message");
            }

            _logger.LogInformation("Final assistant message: {Message}", assistantMessage);

            var responseMessage = new ChatMessage
            {
                Id = Guid.NewGuid().ToString(),
                Role = "assistant",
                Content = assistantMessage,
                Timestamp = DateTime.UtcNow,
                SessionId = request.SessionId,
                UserId = request.UserId
            };

            await _chatHistoryService.SaveMessageAsync(responseMessage);

            var chatResponse = new ChatCompletionResponse
            {
                Message = responseMessage
            };            return Ok(chatResponse);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error processing chat completion for session {SessionId}", request.SessionId);
            return StatusCode(500, new { error = "Failed to process chat completion" });
        }
    }private List<object> ConvertMcpToolsToAzureFormat(IEnumerable<McpTool> mcpTools)
    {
        var azureTools = new List<object>();
        
        foreach (var tool in mcpTools)
        {
            object parameters;
            if (tool.InputSchema != null)
            {
                parameters = new
                {
                    type = "object",
                    properties = tool.InputSchema.Properties,
                    required = tool.InputSchema.Required
                };
            }
            else
            {
                parameters = new 
                { 
                    type = "object", 
                    properties = new Dictionary<string, object>() 
                };
            }

            var azureTool = new
            {
                type = "function",
                function = new
                {
                    name = tool.Name,
                    description = tool.Description,
                    parameters = parameters
                }
            };
            azureTools.Add(azureTool);
        }

        return azureTools;
    }
}

public class CreateSessionRequest
{
    public string UserId { get; set; } = string.Empty;
    public string Title { get; set; } = string.Empty;
}
