import { BaseService } from './BaseService';

export class ModelService extends BaseService {
    private static instance = new ModelService(); // Create an instance of the service

    // Get the list of available models
    public static getAvailableModels = async (accessToken: string): Promise<string[]> => {
        try {
            const result = await this.instance.getResponseAsync<string[]>(
                {
                    commandPath: 'model/GetModels',
                    method: 'GET',
                },
                accessToken, // Include the access token here
            );
            return result;
        } catch (error: unknown) {
            if (error instanceof Error) {
                console.error('Error fetching models:', error.message);
            } else {
                console.error('An unknown error occurred while fetching models.');
            }
            return []; // Return an empty array in case of error
        }
    };

    // Get the user's selected model
    public static getUserModel = async (accessToken: string): Promise<string> => {
        try {
            const result = await this.instance.getResponseAsync<string>(
                {
                    commandPath: 'model/GetUserModel',
                    method: 'GET',
                },
                accessToken, // Include the access token here
            );
            return result;
        } catch (error: unknown) {
            if (error instanceof Error) {
                console.error('Error fetching user model:', error.message);
            } else {
                console.error('An unknown error occurred while fetching user model.');
            }
            return ''; // Return an empty string in case of error
        }
    };

    // Set the user's selected model
    public static setUserModel = async (modelName: string, accessToken: string): Promise<void> => {
        try {
            const result = await this.instance.getResponseAsync<string>(
                {
                    commandPath: 'model/SetUserModel',
                    method: 'POST',
                    body: modelName,
                },
                accessToken, // Include the access token here
            );

            if (result !== 'ok') {
                console.warn('Unexpected response from SetUserModel API.');
            }
        } catch (error: unknown) {
            if (error instanceof Error) {
                console.error('Error setting user model:', error.message);
            } else {
                console.error('An unknown error occurred while setting user model.');
            }
        }
    };
}

