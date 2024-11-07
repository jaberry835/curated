// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

param principalId string
param roleDefinitionId string

param roleAssignmentId string = guid(principalId, roleDefinitionId, resourceGroup().name)

resource symbolicname 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: roleAssignmentId
  scope: resourceGroup()
  properties: {
    principalId: principalId
    roleDefinitionId: roleDefinitionId
    principalType: 'ServicePrincipal'
  }
}
