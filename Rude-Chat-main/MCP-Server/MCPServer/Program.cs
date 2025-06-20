using MCPServer.Services;
using MCPServer.Services.Azure;

var builder = WebApplication.CreateBuilder(args);

// Add services to the container
builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

// Add MCP services
builder.Services.AddScoped<IToolService, ToolService>();
builder.Services.AddScoped<IAzureToolService, AzureResourceToolService>();
builder.Services.AddScoped<IAzureToolService, AzureDataExplorerToolService>();
builder.Services.AddScoped<IAzureDocumentService, AzureDocumentService>();
builder.Services.AddScoped<IChatHistoryService, CosmosChatHistoryService>();
builder.Services.AddHttpClient<AzureResourceToolService>();
builder.Services.AddHttpClient<AzureDataExplorerToolService>();

// Add CORS for production and development
builder.Services.AddCors(options =>
{
    options.AddPolicy("AllowAllOrigins", policy =>
    {
        policy.AllowAnyOrigin()
              .AllowAnyHeader()
              .AllowAnyMethod();
    });
});

// Add logging
builder.Services.AddLogging();

var app = builder.Build();

// Configure the HTTP request pipeline
if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseHttpsRedirection();
app.UseCors("AllowAllOrigins");

// Enable static files for Angular
app.UseStaticFiles();

app.UseRouting();
app.MapControllers();

// Serve static files and provide SPA fallback for non-API routes
app.MapFallback(async context =>
{
    // Only fallback to index.html for non-API routes
    if (!context.Request.Path.StartsWithSegments("/api"))
    {
        context.Response.ContentType = "text/html";
        await context.Response.SendFileAsync(Path.Combine(app.Environment.WebRootPath, "index.html"));
    }
    else
    {
        context.Response.StatusCode = 404;
    }
});

// Add a health check endpoint
app.MapGet("/health", () => new { 
    status = "healthy", 
    timestamp = DateTime.UtcNow,
    environment = app.Environment.EnvironmentName
});

app.Run();
