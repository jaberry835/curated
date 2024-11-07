// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using CopilotChat.WebApi.Models.Storage;

namespace CopilotChat.WebApi.Storage;

/// <summary>
/// Repository for managing UserPreferences in CosmosDB.
/// </summary>
public class ChatPreferenceRepository : Repository<ChatPreference>
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ChatPreferenceRepository"/> class.
    /// </summary>
    /// <param name="storageContext">The storage context for CosmosDB.</param>
    public ChatPreferenceRepository(IStorageContext<ChatPreference> storageContext)
        : base(storageContext)
    {
    }

    /// <summary>
    /// Retrieves the user preference for a specific user by UserId.
    /// </summary>
    /// <param name="userId">The user's ID.</param>
    /// <returns>The user's model preference.</returns>
    public async Task<ChatPreference> GetUserPreferenceAsync(string userId)
    {
        return await this.StorageContext.ReadAsync(userId, userId);
    }

    /// <summary>
    /// Saves or updates the user preference.
    /// </summary>
    /// <param name="userPreference">The user's preference to save.</param>
    /// <returns>A task to await the operation.</returns>
    public async Task SaveUserPreferenceAsync(ChatPreference userPreference)
    {
        await this.StorageContext.UpsertAsync(userPreference);
    }
}
