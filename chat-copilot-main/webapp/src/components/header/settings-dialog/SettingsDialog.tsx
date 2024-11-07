// Copyright (c) Microsoft. All rights reserved.

import {
    Accordion,
    AccordionHeader,
    AccordionItem,
    AccordionPanel,
    Body1,
    Button,
    Dialog,
    DialogActions,
    DialogBody,
    DialogContent,
    DialogOpenChangeData,
    DialogSurface,
    DialogTitle,
    DialogTrigger,
    Divider,
    Dropdown,
    Label,
    makeStyles,
    Option,
    shorthands,
    tokens,
} from '@fluentui/react-components';
import React, { useEffect, useState } from 'react';
import { useMsal } from '@azure/msal-react'; // Ensure correct imports
import { useAppSelector } from '../../../redux/app/hooks';
import { RootState } from '../../../redux/app/store';
import { SharedStyles, useDialogClasses } from '../../../styles';
import { TokenUsageGraph } from '../../token-usage/TokenUsageGraph';
import { SettingSection } from './SettingSection';
import { AuthHelper } from '../../../libs/auth/AuthHelper';
import { ModelService } from '../../../libs/services/ModelService'; // New Service for interacting with API

const useClasses = makeStyles({
    root: {
        ...shorthands.overflow('hidden'),
        display: 'flex',
        flexDirection: 'column',
        height: '600px',
    },
    outer: {
        paddingRight: tokens.spacingVerticalXS,
    },
    content: {
        height: '100%',
        ...SharedStyles.scroll,
        paddingRight: tokens.spacingVerticalL,
    },
    footer: {
        paddingTop: tokens.spacingVerticalL,
    },
    dropdownSection: {
        marginBottom: tokens.spacingVerticalL,
    },
});

interface ISettingsDialogProps {
    open: boolean;
    closeDialog: () => void;
}

export const SettingsDialog: React.FC<ISettingsDialogProps> = ({ open, closeDialog }) => {
    const classes = useClasses();
    const dialogClasses = useDialogClasses();
    const { serviceInfo, settings, tokenUsage } = useAppSelector((state: RootState) => state.app);
    const { instance, inProgress } = useMsal();
    const [models, setModels] = useState<string[]>([]);
    const [selectedModel, setSelectedModel] = useState<string>('');
    const [loadingModels, setLoadingModels] = useState<boolean>(true);

     useEffect(() => {
         const fetchModels = async () => {
             
             console.log('Fetching models...');
             try {
                 setLoadingModels(true);
                 const accessToken = await AuthHelper.getSKaaSAccessToken(instance, inProgress);
                 const availableModels = await ModelService.getAvailableModels(accessToken);
                 setModels(availableModels);
                 console.log('Available models:', availableModels);

                 // Fetch user model or set default model
                 const userModel = await ModelService.getUserModel(accessToken);
                 setSelectedModel(userModel);
                 console.log('User selected model:', userModel);
             } catch (error) {
                 console.error('Error fetching models:', error);
             } finally {
                 setLoadingModels(false);
             }
         };

         if (open) {
             void fetchModels();
         }
     }, [open]);

        const handleModelChange = (_: any, data: { optionValue?: string }) => {
            if (data.optionValue && data.optionValue !== selectedModel) {
                // Call an async function to handle the model change
                void handleModelChangeAsync(data.optionValue);
            }
        };

        const handleModelChangeAsync = async (modelName: string) => {
            try {
                setSelectedModel(modelName);

                if (inProgress === 'none') {
                    const accessToken = await AuthHelper.getSKaaSAccessToken(instance, inProgress);
                    await ModelService.setUserModel(modelName, accessToken);
                    console.log('User model set successfully');
                } else {
                    console.warn('Authentication is in progress, please wait...');
                }
            } catch (error) {
                console.error('Error setting user model:', error);
            }
        };

    return (
        <Dialog
            open={open}
            onOpenChange={(_ev: any, data: DialogOpenChangeData) => {
                if (!data.open) closeDialog();
            }}
        >
            <DialogSurface className={classes.outer}>
                <DialogBody className={classes.root}>
                    <DialogTitle>Settings</DialogTitle>
                    <DialogContent className={classes.content}>
                        <TokenUsageGraph tokenUsage={tokenUsage} />

                        {/* New AOAI Model Selection Section */}
                        <Divider />

                        <Divider />

                        <Accordion collapsible multiple defaultOpenItems={['basic', 'aoai-model']}>
                            <AccordionItem value="aoai-model">
                                <AccordionHeader expandIconPosition="end">
                                    <h3>AOAI Model</h3>
                                </AccordionHeader>
                                <AccordionPanel className={classes.dropdownSection}>
                                    {loadingModels ? (
                                        <Body1 color={tokens.colorNeutralForeground3}>Loading models...</Body1>
                                    ) : (
                                        <Dropdown
                                            placeholder="Select a model"
                                            value={selectedModel}
                                            onOptionSelect={handleModelChange}
                                        >
                                            {models.map((model) => (
                                                <Option key={model} value={model}>
                                                    {model}
                                                </Option>
                                            ))}
                                        </Dropdown>
                                    )}
                                </AccordionPanel>
                            </AccordionItem>
                            <AccordionItem value="basic">
                                <AccordionHeader expandIconPosition="end">
                                    <h3>Basic</h3>
                                </AccordionHeader>
                                <AccordionPanel>
                                    <SettingSection key={settings[0].title} setting={settings[0]} contentOnly />
                                </AccordionPanel>
                            </AccordionItem>
                            <Divider />
                            <AccordionItem value="advanced">
                                <AccordionHeader expandIconPosition="end" data-testid="advancedSettingsFoldup">
                                    <h3>Advanced</h3>
                                </AccordionHeader>
                                <AccordionPanel>
                                    <Body1 color={tokens.colorNeutralForeground3}>
                                        Some settings are disabled by default as they are not fully supported yet.
                                    </Body1>
                                    {settings.slice(1).map((setting) => {
                                        return <SettingSection key={setting.title} setting={setting} />;
                                    })}
                                </AccordionPanel>
                            </AccordionItem>
                            <Divider />
                            <AccordionItem value="about">
                                <AccordionHeader expandIconPosition="end">
                                    <h3>About</h3>
                                </AccordionHeader>
                                <AccordionPanel>
                                    <Body1 color={tokens.colorNeutralForeground3}>
                                        Backend version: {serviceInfo.version}
                                        <br />
                                        Frontend version: {process.env.REACT_APP_SK_VERSION ?? '-'}
                                        <br />
                                        {process.env.REACT_APP_SK_BUILD_INFO}
                                    </Body1>
                                </AccordionPanel>
                            </AccordionItem>
                            <Divider />
                        </Accordion>
                    </DialogContent>
                </DialogBody>
                <DialogActions position="start" className={dialogClasses.footer}>
                    <Label size="small" color="brand" className={classes.footer}>
                        Join the Semantic Kernel open source community!{' '}
                        <a href="https://aka.ms/semantic-kernel" target="_blank" rel="noreferrer">
                            Learn More
                        </a>
                    </Label>
                    <DialogTrigger disableButtonEnhancement>
                        <Button appearance="secondary" data-testid="userSettingsCloseButton">
                            Close
                        </Button>
                    </DialogTrigger>
                </DialogActions>
            </DialogSurface>
        </Dialog>
    );
};
