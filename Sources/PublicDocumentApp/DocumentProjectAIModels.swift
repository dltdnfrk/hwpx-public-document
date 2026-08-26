import Foundation

struct AIProposalHistoryRecord: Codable, Equatable {
    let proposalID: String
    let baseRevisionID: String
    let state: String
    let targetElementIDs: [String]
    let operation: String
    let provider: String
    let endpointIdentity: String
    let payloadScope: String
    let commands: [AIProposalCommand]
    let diffs: [AIProposalDiff]
    let approvedCommandIDs: [String]
    let createdRevisionID: String?

    init(
        proposalID: String,
        baseRevisionID: String,
        state: String,
        targetElementIDs: [String],
        operation: String = "",
        provider: String = "",
        endpointIdentity: String = "",
        payloadScope: String = "",
        commands: [AIProposalCommand] = [],
        diffs: [AIProposalDiff] = [],
        approvedCommandIDs: [String] = [],
        createdRevisionID: String? = nil
    ) {
        self.proposalID = proposalID
        self.baseRevisionID = baseRevisionID
        self.state = state
        self.targetElementIDs = targetElementIDs
        self.operation = operation
        self.provider = provider
        self.endpointIdentity = endpointIdentity
        self.payloadScope = payloadScope
        self.commands = commands
        self.diffs = diffs
        self.approvedCommandIDs = approvedCommandIDs
        self.createdRevisionID = createdRevisionID
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        proposalID = try values.decode(String.self, forKey: .proposalID)
        baseRevisionID = try values.decode(String.self, forKey: .baseRevisionID)
        state = try values.decode(String.self, forKey: .state)
        targetElementIDs = try values.decode([String].self, forKey: .targetElementIDs)
        operation = try values.decodeIfPresent(String.self, forKey: .operation) ?? ""
        provider = try values.decodeIfPresent(String.self, forKey: .provider) ?? ""
        endpointIdentity = try values.decodeIfPresent(String.self, forKey: .endpointIdentity) ?? ""
        payloadScope = try values.decodeIfPresent(String.self, forKey: .payloadScope) ?? ""
        commands = try values.decodeIfPresent([AIProposalCommand].self, forKey: .commands) ?? []
        diffs = try values.decodeIfPresent([AIProposalDiff].self, forKey: .diffs) ?? []
        approvedCommandIDs = try values.decodeIfPresent([String].self, forKey: .approvedCommandIDs) ?? []
        createdRevisionID = try values.decodeIfPresent(String.self, forKey: .createdRevisionID)
    }
}

struct AIProposalCommand: Codable, Equatable {
    let commandID: String
    let name: String
    let targetElementID: String
    let value: String
    let targetPath: String?

    init(commandID: String, name: String, targetElementID: String, value: String, targetPath: String? = nil) {
        self.commandID = commandID; self.name = name; self.targetElementID = targetElementID; self.value = value; self.targetPath = targetPath
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        commandID = try c.decode(String.self, forKey: .commandID); name = try c.decode(String.self, forKey: .name)
        targetElementID = try c.decode(String.self, forKey: .targetElementID); value = try c.decode(String.self, forKey: .value)
        targetPath = try c.decodeIfPresent(String.self, forKey: .targetPath)
    }
}

struct AIProviderConfiguration: Codable, Equatable {
    let provider: String
    let endpointIdentity: String
    let model: String?
    let keychainAccountReference: String

    init(
        provider: String,
        endpointIdentity: String,
        model: String? = nil,
        keychainAccountReference: String
    ) {
        self.provider = provider
        self.endpointIdentity = endpointIdentity
        self.model = model
        self.keychainAccountReference = keychainAccountReference
    }
}

struct AIConsentGrant: Codable, Equatable {
    let grantID: String
    let documentID: String
    let provider: String
    let endpointIdentity: String
    let model: String?
    let operation: String
    let payloadScope: String
    let revoked: Bool

    init(
        grantID: String,
        documentID: String,
        provider: String,
        endpointIdentity: String,
        model: String? = nil,
        operation: String,
        payloadScope: String,
        revoked: Bool
    ) {
        self.grantID = grantID
        self.documentID = documentID
        self.provider = provider
        self.endpointIdentity = endpointIdentity
        self.model = model
        self.operation = operation
        self.payloadScope = payloadScope
        self.revoked = revoked
    }
}
