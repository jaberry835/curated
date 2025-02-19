// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json.Serialization;
using CopilotChat.WebApi.Storage;

namespace CopilotChat.WebApi.Models.Storage;

/// <summary>
/// A chat participant is a user that is part of a chat.
/// A user can be part of multiple chats, thus a user can have multiple chat participants.
/// </summary>
public class ChatPreference : IStorageEntity
{
    /// <summary>
    /// Participant ID that is persistent and unique.
    /// </summary>
    public string Id { get; set; }

    /// <summary>
    /// User ID that is persistent and unique.
    /// </summary>
    public string UserId { get; set; }

    /// <summary>
    /// Chat ID that this participant belongs to.
    /// </summary>
    public string ModelName { get; set; }

    /// <summary>
    /// The partition key for the source.
    /// </summary>
    [JsonIgnore]
    public string Partition => this.UserId;

    public ChatPreference(string userId, string ModelName)
    {
        this.Id = userId;
        this.UserId = userId;
        this.ModelName = ModelName;
    }
}
