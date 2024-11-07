// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading.Tasks;
using CopilotChat.WebApi.Auth;
using CopilotChat.WebApi.Storage;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using Microsoft.KernelMemory;
using Microsoft.SemanticKernel;

namespace CopilotChat.WebApi.Services;

/// <summary>
/// Extension methods for registering Semantic Kernel related services.
/// </summary>
public sealed class SemanticKernelProvider
{
    private Kernel _kernel;
    private readonly IConfiguration _configuration;
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly IServiceProvider _serviceProvider;
    private string? _azureAIDeployment;
    private readonly ChatPreferenceRepository _chatPreferenceRepository;
    public SemanticKernelProvider(
        IServiceProvider serviceProvider,
        IConfiguration configuration,
        IHttpClientFactory httpClientFactory,
        ChatPreferenceRepository chatPreferenceRepository)
    {
        this._configuration = configuration;
        this._httpClientFactory = httpClientFactory;
        this._serviceProvider = serviceProvider;
        this._chatPreferenceRepository = chatPreferenceRepository ?? throw new ArgumentNullException(nameof(chatPreferenceRepository));

        // Initialize kernel with the default deployment from appsettings.json or user preferences
        this._kernel = this.InitializeCompletionKernel(serviceProvider).Result;
    }


    /// <summary>
    /// Produce semantic-kernel with only completion services for chat.
    /// </summary>
    public Kernel GetCompletionKernel() => this._kernel.Clone();

    /// <summary>
    /// Update the Azure OpenAI deployment dynamically.
    /// </summary>
    public void UpdateAzureAIDeployment(string newDeployment)
    {
        if (!string.IsNullOrEmpty(newDeployment))
        {
            this._azureAIDeployment = newDeployment;
            // Reinitialize the kernel with the new deployment name
            this._kernel = this.InitializeCompletionKernel(this._serviceProvider).Result;
        }
    }

    private async Task<Kernel> InitializeCompletionKernel(IServiceProvider serviceProvider)
    {
        var builder = Kernel.CreateBuilder();
        builder.Services.AddLogging();

        // Fetch KernelMemoryConfig
        var memoryOptions = serviceProvider?.GetRequiredService<IOptions<KernelMemoryConfig>>().Value;


        // Retrieve the user's deployment asynchronously, inside a scoped context
        using (var scope = serviceProvider.CreateScope())
        {
            var authInfo = scope.ServiceProvider.GetRequiredService<IAuthInfo>();
            string userId = authInfo.UserId;
            string? userDeployment = null;
            //var userPreference = await this._chatPreferenceRepository.GetUserPreferenceAsync(userId);
            try
            {
                // Retrieve the user's model preference
                var userPreference = await this._chatPreferenceRepository.GetUserPreferenceAsync(userId);
                userDeployment = userPreference.ModelName;
            }
            catch (KeyNotFoundException)
            {
                // User preference not found, proceed to load default
            }

            switch (memoryOptions.TextGeneratorType)
            {
                case string x when x.Equals("AzureOpenAI", StringComparison.OrdinalIgnoreCase):
                case string y when y.Equals("AzureOpenAIText", StringComparison.OrdinalIgnoreCase):
                    var azureAIOptions = memoryOptions.GetServiceConfig<AzureOpenAIConfig>(this._configuration, "AzureOpenAIText");
                    this._azureAIDeployment = userDeployment ?? this._azureAIDeployment ?? azureAIOptions.Deployment;
#pragma warning disable CA2000 // No need to dispose of HttpClient instances from IHttpClientFactory
                    builder.AddAzureOpenAIChatCompletion(
                        this._azureAIDeployment,
                        azureAIOptions.Endpoint,
                        azureAIOptions.APIKey,
                        httpClient: this._httpClientFactory.CreateClient());
                    break;

                case string x when x.Equals("OpenAI", StringComparison.OrdinalIgnoreCase):
                    var openAIOptions = memoryOptions.GetServiceConfig<OpenAIConfig>(this._configuration, "OpenAI");
                    builder.AddOpenAIChatCompletion(
                        openAIOptions.TextModel,
                        openAIOptions.APIKey,
                        httpClient: this._httpClientFactory.CreateClient());
#pragma warning restore CA2000
                    break;

                default:
                    throw new ArgumentException($"Invalid {nameof(memoryOptions.TextGeneratorType)} value in 'KernelMemory' settings.");
            }
        }
        return builder.Build();
    }
}
