//
//  SharedSyncUseCaseFactory.swift
//  Epilogue
//
//  Created on 2026-03-07.
//

import Foundation
import Domain
import EpilogueShared

struct SharedFeedSyncResult {
    enum Kind {
        case success(pushed: Bool, updatedFeeds: Int, deletedFeeds: Int)
        case error(message: String)
        case notConfigured
    }

    let kind: Kind
}

enum SharedDigestSyncPlan {
    case combined(digests: [GWSyncDigest], shouldDownloadEpubs: Bool)
    case legacy(digests: [GWDigestResponse], shouldDownloadEpubs: Bool)
    case error(message: String)
    case notConfigured
}

@MainActor
final class SharedConfigSyncBridge {
    private let useCase: ConfigSyncUseCase

    init(settingsRepository: SettingsRepositoryProtocol) {
        let settings = IOSSettingsPortAdapter(settingsRepository: settingsRepository)
        let ghostwriter = IOSGhostwriterSyncPortAdapter(settingsRepository: settingsRepository)
        self.useCase = ConfigSyncUseCase(settings: settings, ghostwriter: ghostwriter)
    }

    func syncConfig() async throws -> Bool {
        try await useCase.syncConfig()
    }

    func applyPreFetchedConfig(_ config: GWClientConfigResponse) async throws -> Bool {
        try await useCase.applyPreFetchedConfig(config: toSharedConfigResponse(config))
    }

    func pushMinWordCount(_ count: Int) async throws -> Bool {
        try await useCase.pushMinWordCount(count: Int32(count))
    }
}

@MainActor
final class SharedFeedSyncBridge {
    private let useCase: FeedSyncUseCase

    init(settingsRepository: SettingsRepositoryProtocol, feedRepository: FeedRepositoryProtocol) {
        let settings = IOSSettingsPortAdapter(settingsRepository: settingsRepository)
        let feedStore = IOSFeedStorePortAdapter(feedRepository: feedRepository)
        let ghostwriter = IOSGhostwriterSyncPortAdapter(settingsRepository: settingsRepository)

        self.useCase = FeedSyncUseCase(
            settings: settings,
            feedStore: feedStore,
            ghostwriter: ghostwriter,
            nowProviderMillis: {
                KotlinLong(longLong: Int64((Date().timeIntervalSince1970 * 1000).rounded()))
            }
        )
    }

    func sync() async throws -> SharedFeedSyncResult.Kind {
        let outcome = try await useCase.sync()
        switch outcome {
        case let success as FeedSyncOutcomeSuccess:
            return .success(
                pushed: success.pushed,
                updatedFeeds: Int(success.updatedFeeds),
                deletedFeeds: Int(success.deletedFeeds)
            )
        case let error as FeedSyncOutcomeError:
            return .error(message: error.message)
        case _ as FeedSyncOutcomeNotConfigured:
            return .notConfigured
        default:
            return .error(message: "Unexpected feed sync outcome")
        }
    }
}

@MainActor
final class SharedDigestSyncBridge {
    private let useCase: DigestSyncUseCase

    init(settingsRepository: SettingsRepositoryProtocol, digestRepository: DigestRepositoryProtocol) {
        let settings = IOSSettingsPortAdapter(settingsRepository: settingsRepository)
        let digestStore = IOSDigestStorePortAdapter(digestRepository: digestRepository)
        let ghostwriter = IOSGhostwriterSyncPortAdapter(settingsRepository: settingsRepository)
        self.useCase = DigestSyncUseCase(settings: settings, digestStore: digestStore, ghostwriter: ghostwriter)
    }

    func planSync() async throws -> SharedDigestSyncPlan {
        let plan = try await useCase.planSync()
        switch plan {
        case let combined as DigestSyncPlanCombined:
            return .combined(
                digests: combined.digests.map(fromSharedSyncDigest),
                shouldDownloadEpubs: combined.shouldDownloadEpubs
            )
        case let legacy as DigestSyncPlanLegacy:
            return .legacy(
                digests: legacy.digests.map(fromSharedDigestResponse),
                shouldDownloadEpubs: legacy.shouldDownloadEpubs
            )
        case let error as DigestSyncPlanError:
            return .error(message: error.message)
        case _ as DigestSyncPlanNotConfigured:
            return .notConfigured
        default:
            return .error(message: "Unexpected digest sync plan")
        }
    }
}

@MainActor
func makeSharedConfigSyncBridge(settingsRepository: SettingsRepositoryProtocol) -> SharedConfigSyncBridge {
    SharedConfigSyncBridge(settingsRepository: settingsRepository)
}

@MainActor
func makeSharedFeedSyncBridge(
    settingsRepository: SettingsRepositoryProtocol,
    feedRepository: FeedRepositoryProtocol
) -> SharedFeedSyncBridge {
    SharedFeedSyncBridge(settingsRepository: settingsRepository, feedRepository: feedRepository)
}

@MainActor
func makeSharedDigestSyncBridge(
    settingsRepository: SettingsRepositoryProtocol,
    digestRepository: DigestRepositoryProtocol
) -> SharedDigestSyncBridge {
    SharedDigestSyncBridge(settingsRepository: settingsRepository, digestRepository: digestRepository)
}

private final class IOSSettingsPortAdapter: NSObject, SettingsPort {
    private let settingsRepository: SettingsRepositoryProtocol

    init(settingsRepository: SettingsRepositoryProtocol) {
        self.settingsRepository = settingsRepository
    }

    func isGhostwriterConfigured(completionHandler: @escaping (KotlinBoolean?, Error?) -> Void) {
        Task {
            do { completionHandler(KotlinBoolean(bool: try await settingsRepository.isGhostwriterConfigured()), nil) }
            catch { completionHandler(nil, error) }
        }
    }

    func getConfigUpdatedAt(completionHandler: @escaping (String?, Error?) -> Void) {
        Task {
            do { completionHandler(try await settingsRepository.getGhostwriterConfigUpdatedAt(), nil) }
            catch { completionHandler(nil, error) }
        }
    }

    func setConfigUpdatedAt(value: String?, completionHandler: @escaping (Error?) -> Void) {
        Task {
            do {
                try await settingsRepository.setGhostwriterConfigUpdatedAt(value)
                completionHandler(nil)
            } catch {
                completionHandler(error)
            }
        }
    }

    func getMinWordCount(completionHandler: @escaping (KotlinInt?, Error?) -> Void) {
        Task {
            do { completionHandler(KotlinInt(int: Int32(try await settingsRepository.getMinWordCount())), nil) }
            catch { completionHandler(nil, error) }
        }
    }

    func setMinWordCount(value: Int32, completionHandler: @escaping (Error?) -> Void) {
        Task {
            do {
                try await settingsRepository.setMinWordCount(Int(value))
                completionHandler(nil)
            } catch {
                completionHandler(error)
            }
        }
    }

    func getGhostwriterSchedule(completionHandler: @escaping (GhostwriterScheduleSnapshot?, Error?) -> Void) {
        Task {
            do {
                let schedule = try await settingsRepository.getGhostwriterSchedule()
                completionHandler(schedule.map(toSharedScheduleSnapshot), nil)
            } catch {
                completionHandler(nil, error)
            }
        }
    }

    func setGhostwriterSchedule(value: GhostwriterScheduleSnapshot, completionHandler: @escaping (Error?) -> Void) {
        Task {
            do {
                try await settingsRepository.setGhostwriterSchedule(
                    morningHour: Int(value.morningHour),
                    morningMinute: Int(value.morningMinute),
                    noonHour: Int(value.noonHour),
                    noonMinute: Int(value.noonMinute),
                    eveningHour: Int(value.eveningHour),
                    eveningMinute: Int(value.eveningMinute),
                    timezone: value.timezone
                )
                completionHandler(nil)
            } catch {
                completionHandler(error)
            }
        }
    }

    func getLastFeedSyncTimeMillis(completionHandler: @escaping (KotlinLong?, Error?) -> Void) {
        Task {
            do {
                let value = try await settingsRepository.getLastFeedSyncTime().map { KotlinLong(longLong: $0.epochMillis) }
                completionHandler(value, nil)
            } catch {
                completionHandler(nil, error)
            }
        }
    }

    func setLastFeedSyncTimeMillis(value: Int64, completionHandler: @escaping (Error?) -> Void) {
        Task {
            do {
                try await settingsRepository.setLastFeedSyncTime(Date(epochMillis: value))
                completionHandler(nil)
            } catch {
                completionHandler(error)
            }
        }
    }

    func getLastDigestSyncTimeMillis(completionHandler: @escaping (KotlinLong?, Error?) -> Void) {
        Task {
            do {
                let value = try await settingsRepository.getLastDigestSyncTime().map { KotlinLong(longLong: $0.epochMillis) }
                completionHandler(value, nil)
            } catch {
                completionHandler(nil, error)
            }
        }
    }

    func setLastDigestSyncTimeMillis(value: Int64, completionHandler: @escaping (Error?) -> Void) {
        Task {
            do {
                try await settingsRepository.setLastDigestSyncTime(Date(epochMillis: value))
                completionHandler(nil)
            } catch {
                completionHandler(error)
            }
        }
    }

    func shouldDownloadGhostwriterEpubsOnSync(completionHandler: @escaping (KotlinBoolean?, Error?) -> Void) {
        Task {
            do { completionHandler(KotlinBoolean(bool: try await settingsRepository.getGhostwriterDownloadEpubsOnSync()), nil) }
            catch { completionHandler(nil, error) }
        }
    }
}

private final class IOSFeedStorePortAdapter: NSObject, FeedStorePort {
    private let feedRepository: FeedRepositoryProtocol

    init(feedRepository: FeedRepositoryProtocol) {
        self.feedRepository = feedRepository
    }

    func getAllFeeds(completionHandler: @escaping ([EpilogueShared.Feed]?, Error?) -> Void) {
        Task {
            do {
                let feeds = try await feedRepository.getAllFeeds().map(toSharedFeed)
                completionHandler(feeds, nil)
            } catch {
                completionHandler(nil, error)
            }
        }
    }

    func upsertAll(feeds: [EpilogueShared.Feed], completionHandler: @escaping (Error?) -> Void) {
        Task {
            do {
                try await feedRepository.upsertAll(feeds.map(toDomainFeed))
                completionHandler(nil)
            } catch {
                completionHandler(error)
            }
        }
    }

    func deleteByUrls(urls: [String], completionHandler: @escaping (Error?) -> Void) {
        Task {
            do {
                try await feedRepository.deleteByURLs(urls)
                completionHandler(nil)
            } catch {
                completionHandler(error)
            }
        }
    }

    func clearAllLocallyModified(completionHandler: @escaping (Error?) -> Void) {
        Task {
            do {
                try await feedRepository.clearAllLocallyModified()
                completionHandler(nil)
            } catch {
                completionHandler(error)
            }
        }
    }
}

private final class IOSDigestStorePortAdapter: NSObject, DigestStorePort {
    private let digestRepository: DigestRepositoryProtocol

    init(digestRepository: DigestRepositoryProtocol) {
        self.digestRepository = digestRepository
    }

    func getAllRemoteIds(completionHandler: @escaping ([String]?, Error?) -> Void) {
        Task {
            do { completionHandler(try await digestRepository.getAllRemoteIds(), nil) }
            catch { completionHandler(nil, error) }
        }
    }
}

private final class IOSGhostwriterSyncPortAdapter: NSObject, GhostwriterSyncPort {
    private let settingsRepository: SettingsRepositoryProtocol

    init(settingsRepository: SettingsRepositoryProtocol) {
        self.settingsRepository = settingsRepository
    }

    func getConfig(completionHandler: @escaping (SyncPortResult<EpilogueShared.ClientConfigResponse>?, Error?) -> Void) {
        Task {
            do {
                let client = try await makeClient()
                let response = try await client.getConfig()
                completionHandler(SyncPortResultSuccess(data: toSharedConfigResponse(response)), nil)
            } catch {
                completionHandler(mapErrorToResult(error), nil)
            }
        }
    }

    func updateConfig(
        request: EpilogueShared.ClientConfigUpdateRequest,
        completionHandler: @escaping (SyncPortResult<EpilogueShared.ClientConfigResponse>?, Error?) -> Void
    ) {
        Task {
            do {
                let client = try await makeClient()
                let response = try await client.updateConfig(fromSharedConfigUpdate(request))
                completionHandler(SyncPortResultSuccess(data: toSharedConfigResponse(response)), nil)
            } catch {
                completionHandler(mapErrorToResult(error), nil)
            }
        }
    }

    func syncFeeds(
        feeds: [EpilogueShared.FeedSyncRequest],
        completionHandler: @escaping (SyncPortResult<EpilogueShared.FeedSyncResponse>?, Error?) -> Void
    ) {
        Task {
            do {
                let client = try await makeClient()
                let response = try await client.syncFeeds(feeds.map(fromSharedFeedSyncRequest))
                completionHandler(SyncPortResultSuccess(data: toSharedFeedSyncResponse(response)), nil)
            } catch {
                completionHandler(mapErrorToResult(error), nil)
            }
        }
    }

    func getFeedChanges(
        since: String?,
        completionHandler: @escaping (SyncPortResult<EpilogueShared.FeedChangesResponse>?, Error?) -> Void
    ) {
        Task {
            do {
                let client = try await makeClient()
                let response = try await client.getFeedChanges(since: since?.toISO8601Date())
                completionHandler(SyncPortResultSuccess(data: toSharedFeedChangesResponse(response)), nil)
            } catch {
                completionHandler(mapErrorToResult(error), nil)
            }
        }
    }

    func performSync(
        feedSince: String?,
        digestIds: String?,
        completionHandler: @escaping (SyncPortResult<EpilogueShared.SyncResponse>?, Error?) -> Void
    ) {
        Task {
            do {
                let client = try await makeClient()
                let response = try await client.performSync(
                    feedSince: feedSince?.toISO8601Date(),
                    knownDigestIds: digestIds?.split(separator: ",").map(String.init) ?? []
                )
                completionHandler(SyncPortResultSuccess(data: toSharedSyncResponse(response)), nil)
            } catch {
                completionHandler(mapErrorToResult(error), nil)
            }
        }
    }

    func listDigests(completionHandler: @escaping (SyncPortResult<NSArray>?, Error?) -> Void) {
        Task {
            do {
                let client = try await makeClient()
                let response = try await client.listDigests(limit: 200, offset: 0, status: nil)
                let boxed = response.map(toSharedDigestResponse) as NSArray
                let success = SyncPortResultSuccess<NSArray>(data: boxed)
                let typed = unsafeBitCast(success, to: SyncPortResult<NSArray>.self)
                completionHandler(typed, nil)
            } catch {
                completionHandler(mapErrorToResult(error), nil)
            }
        }
    }

    func getDigestArticles(
        digestId: String,
        completionHandler: @escaping (SyncPortResult<EpilogueShared.DigestArticlesResponse>?, Error?) -> Void
    ) {
        Task {
            do {
                let client = try await makeClient()
                let response = try await client.getDigestArticles(id: digestId)
                completionHandler(SyncPortResultSuccess(data: toSharedDigestArticlesResponse(response)), nil)
            } catch {
                completionHandler(mapErrorToResult(error), nil)
            }
        }
    }

    private func makeClient() async throws -> GWClient {
        guard let url = try await settingsRepository.getGhostwriterURL() else {
            throw GWError.notConfigured
        }
        let apiKey = try await settingsRepository.getGhostwriterAPIKey()
        return try GWClient(baseURLString: url, apiKey: apiKey)
    }

    private func mapErrorToResult<T>(_ error: Error) -> SyncPortResult<T> {
        let mapped: SyncPortResult<KotlinNothing>
        if let ghostwriterError = error as? GWError {
            switch ghostwriterError {
            case .notConfigured:
                mapped = SyncPortResultNotConfigured()
            case .conflict:
                mapped = SyncPortResultError(message: ghostwriterError.localizedDescription, code: KotlinInt(int: 409))
            case .httpError(let statusCode, let message):
                mapped = SyncPortResultError(
                    message: message ?? "HTTP \(statusCode)",
                    code: KotlinInt(int: Int32(statusCode))
                )
            default:
                mapped = SyncPortResultError(message: ghostwriterError.localizedDescription, code: nil)
            }
        } else {
            mapped = SyncPortResultError(message: error.localizedDescription, code: nil)
        }
        return unsafeBitCast(mapped, to: SyncPortResult<T>.self)
    }
}

private extension Date {
    var epochMillis: Int64 {
        Int64((timeIntervalSince1970 * 1000).rounded())
    }

    init(epochMillis: Int64) {
        self = Date(timeIntervalSince1970: TimeInterval(epochMillis) / 1000)
    }
}

private func toSharedScheduleSnapshot(_ schedule: Domain.GhostwriterSchedule) -> GhostwriterScheduleSnapshot {
    GhostwriterScheduleSnapshot(
        morningHour: Int32(schedule.morningHour),
        morningMinute: Int32(schedule.morningMinute),
        noonHour: Int32(schedule.noonHour),
        noonMinute: Int32(schedule.noonMinute),
        eveningHour: Int32(schedule.eveningHour),
        eveningMinute: Int32(schedule.eveningMinute),
        timezone: schedule.timezone
    )
}

private func toDomainFeed(_ feed: EpilogueShared.Feed) -> GWFeed {
    GWFeed(
        url: feed.url,
        name: feed.name,
        mode: feed.mode == .briefing ? .briefing : .fidelity,
        lastFetched: feed.lastFetchedEpochMillis,
        maxArticles: Int(feed.maxArticles),
        isEnabled: feed.isEnabled,
        createdAt: Date(),
        serverUpdatedAt: feed.serverUpdatedAtEpochMillis.map { Date(epochMillis: $0.int64Value) },
        locallyModified: feed.locallyModified
    )
}

private func toSharedFeed(_ feed: GWFeed) -> EpilogueShared.Feed {
    EpilogueShared.Feed(
        url: feed.url,
        name: feed.name,
        mode: feed.mode == .briefing ? .briefing : .fidelity,
        lastFetchedEpochMillis: feed.lastFetched,
        maxArticles: Int32(feed.maxArticles),
        isEnabled: feed.isEnabled,
        serverUpdatedAtEpochMillis: feed.serverUpdatedAt.map { KotlinLong(longLong: $0.epochMillis) },
        locallyModified: feed.locallyModified
    )
}

func toSharedConfigResponse(_ response: GWClientConfigResponse) -> EpilogueShared.ClientConfigResponse {
    EpilogueShared.ClientConfigResponse(
        minWordCount: response.minWordCount.map { KotlinInt(int: Int32($0)) },
        morningHour: response.morningHour.map { KotlinInt(int: Int32($0)) },
        morningMinute: response.morningMinute.map { KotlinInt(int: Int32($0)) },
        noonHour: response.noonHour.map { KotlinInt(int: Int32($0)) },
        noonMinute: response.noonMinute.map { KotlinInt(int: Int32($0)) },
        eveningHour: response.eveningHour.map { KotlinInt(int: Int32($0)) },
        eveningMinute: response.eveningMinute.map { KotlinInt(int: Int32($0)) },
        timezone: response.timezone,
        scheduleMorning: response.scheduleMorning,
        scheduleNoon: response.scheduleNoon,
        scheduleEvening: response.scheduleEvening,
        whisperProvider: response.whisperProvider,
        whisperModel: response.whisperModel,
        whisperTimeoutMinutes: response.whisperTimeoutMinutes.map { KotlinInt(int: Int32($0)) },
        mediaProcessingIntervalHours: response.mediaProcessingIntervalHours.map { KotlinInt(int: Int32($0)) },
        includePodcastsInDigest: response.includePodcastsInDigest.map { KotlinBoolean(bool: $0) },
        includeYoutubeInDigest: response.includeYoutubeInDigest.map { KotlinBoolean(bool: $0) },
        pdfEnabled: response.pdfEnabled.map { KotlinBoolean(bool: $0) },
        pdfPageSize: response.pdfPageSize,
        coverEnabled: response.coverEnabled.map { KotlinBoolean(bool: $0) },
        coverProvider: response.coverProvider,
        coverQuality: response.coverQuality,
        coverPrompt: response.coverPrompt,
        coverOverlayEnabled: response.coverOverlayEnabled.map { KotlinBoolean(bool: $0) },
        coverOpenAiApiKey: response.coverOpenAIAPIKey,
        coverGeminiApiKey: response.coverGeminiAPIKey,
        updatedAt: response.updatedAt,
        wallabag: response.wallabag.map { EpilogueShared.IntegrationStatus(enabled: $0.enabled, label: $0.label) },
        newsletters: response.newsletters.map { EpilogueShared.IntegrationStatus(enabled: $0.enabled, label: $0.label) }
    )
}

private func fromSharedConfigUpdate(_ request: EpilogueShared.ClientConfigUpdateRequest) -> GWClientConfigUpdateRequest {
    GWClientConfigUpdateRequest(
        minWordCount: request.minWordCount.map { Int(truncating: $0) },
        morningHour: request.morningHour.map { Int(truncating: $0) },
        morningMinute: request.morningMinute.map { Int(truncating: $0) },
        noonHour: request.noonHour.map { Int(truncating: $0) },
        noonMinute: request.noonMinute.map { Int(truncating: $0) },
        eveningHour: request.eveningHour.map { Int(truncating: $0) },
        eveningMinute: request.eveningMinute.map { Int(truncating: $0) },
        timezone: request.timezone,
        scheduleMorning: request.scheduleMorning,
        scheduleNoon: request.scheduleNoon,
        scheduleEvening: request.scheduleEvening,
        includePodcastsInDigest: request.includePodcastsInDigest?.boolValue,
        includeYoutubeInDigest: request.includeYoutubeInDigest?.boolValue,
        pdfEnabled: request.pdfEnabled?.boolValue,
        pdfPageSize: request.pdfPageSize,
        coverEnabled: request.coverEnabled?.boolValue,
        coverProvider: request.coverProvider,
        coverQuality: request.coverQuality,
        coverPrompt: request.coverPrompt,
        coverOverlayEnabled: request.coverOverlayEnabled?.boolValue,
        clientUpdatedAt: request.clientUpdatedAt
    )
}

private func fromSharedFeedSyncRequest(_ request: EpilogueShared.FeedSyncRequest) -> GWFeedSyncRequest {
    GWFeedSyncRequest(
        url: request.url,
        title: request.title,
        isActive: request.isActive,
        mode: request.mode,
        maxArticles: Int(request.maxArticles)
    )
}

private func toSharedFeedSyncResponse(_ response: GWFeedSyncResponse) -> EpilogueShared.FeedSyncResponse {
    EpilogueShared.FeedSyncResponse(
        synced: Int32(response.synced),
        created: Int32(response.created),
        updated: Int32(response.updated),
        unchanged: Int32(response.unchanged)
    )
}

private func toSharedFeedChangesResponse(_ response: GWFeedChangesResponse) -> EpilogueShared.FeedChangesResponse {
    EpilogueShared.FeedChangesResponse(
        feeds: response.feeds.map { feed in
            EpilogueShared.FeedResponse(
                id: feed.id,
                url: feed.url,
                title: feed.title,
                isActive: feed.isActive,
                mode: feed.mode,
                maxArticles: Int32(feed.maxArticles),
                createdAt: feed.createdAt,
                updatedAt: feed.updatedAt,
                deletedAt: feed.deletedAt
            )
        },
        tombstones: response.tombstones.map { tombstone in
            EpilogueShared.FeedTombstoneResponse(url: tombstone.url, deletedAt: tombstone.deletedAt)
        },
        serverTimestamp: response.serverTimestamp
    )
}

private func toSharedDigestResponse(_ response: GWDigestResponse) -> EpilogueShared.DigestResponse {
    EpilogueShared.DigestResponse(
        id: response.id,
        filename: response.filename,
        availableFormats: response.availableFormats,
        period: response.period,
        status: response.status,
        stage: response.stage,
        articleCount: Int32(response.articleCount),
        errorMessage: response.errorMessage,
        createdAt: response.createdAt,
        completedAt: response.completedAt
    )
}

func fromSharedDigestResponse(_ response: EpilogueShared.DigestResponse) -> GWDigestResponse {
    GWDigestResponse(
        id: response.id,
        filename: response.filename,
        availableFormats: response.availableFormats,
        period: response.period,
        status: response.status,
        stage: response.stage,
        articleCount: Int(response.articleCount),
        errorMessage: response.errorMessage,
        createdAt: response.createdAt,
        completedAt: response.completedAt,
        downloadedAt: nil
    )
}

func fromSharedSyncDigest(_ digest: EpilogueShared.SyncDigest) -> GWSyncDigest {
    GWSyncDigest(
        id: digest.id,
        filename: digest.filename,
        availableFormats: digest.availableFormats,
        period: digest.period,
        status: digest.status,
        stage: digest.stage,
        articleCount: Int(digest.articleCount),
        errorMessage: digest.errorMessage,
        createdAt: digest.createdAt,
        completedAt: digest.completedAt,
        articles: digest.articles.map { article in
            DigestArticleResponse(
                id: article.id,
                title: article.title,
                url: article.url,
                mode: article.mode,
                wordCount: Int(article.wordCount),
                content: article.content,
                contentHTML: article.contentHtml,
                author: article.author,
                feedTitle: article.feedTitle,
                sortOrder: Int(article.sortOrder),
                aiFailed: article.aiFailed
            )
        }
    )
}

private func toSharedDigestArticlesResponse(_ response: GWDigestArticlesResponse) -> EpilogueShared.DigestArticlesResponse {
    EpilogueShared.DigestArticlesResponse(
        digestId: response.digestId,
        articleCount: Int32(response.articleCount),
        articles: response.articles.map { article in
            EpilogueShared.DigestArticleResponse(
                id: article.id,
                title: article.title,
                url: article.url,
                mode: article.mode,
                wordCount: Int32(article.wordCount),
                content: article.content,
                contentHtml: article.contentHTML,
                author: article.author,
                feedTitle: article.feedTitle,
                sortOrder: Int32(article.sortOrder),
                aiFailed: article.aiFailed
            )
        }
    )
}

private func toSharedSyncResponse(_ response: GWSyncResponse) -> EpilogueShared.SyncResponse {
    EpilogueShared.SyncResponse(
        config: toSharedConfigResponse(response.config),
        feeds: toSharedFeedChangesResponse(response.feeds),
        digests: EpilogueShared.SyncDigestsSection(
            newDigests: response.digests.newDigests.map { digest in
                EpilogueShared.SyncDigest(
                    id: digest.id,
                    filename: digest.filename,
                    availableFormats: digest.availableFormats,
                    period: digest.period,
                    status: digest.status,
                    stage: digest.stage,
                    articleCount: Int32(digest.articleCount),
                    errorMessage: digest.errorMessage,
                    createdAt: digest.createdAt,
                    completedAt: digest.completedAt,
                    articles: digest.articles.map { article in
                        EpilogueShared.DigestArticleResponse(
                            id: article.id,
                            title: article.title,
                            url: article.url,
                            mode: article.mode,
                            wordCount: Int32(article.wordCount),
                            content: article.content,
                            contentHtml: article.contentHTML,
                            author: article.author,
                            feedTitle: article.feedTitle,
                            sortOrder: Int32(article.sortOrder),
                            aiFailed: article.aiFailed
                        )
                    }
                )
            }
        ),
        schedules: response.schedules.map { schedule in
            EpilogueShared.ScheduleResponse(
                id: schedule.id,
                period: schedule.period,
                hour: Int32(schedule.hour),
                minute: Int32(schedule.minute),
                enabled: schedule.enabled,
                timezone: schedule.timezone,
                nextRunAt: schedule.nextRunAt
            )
        }
    )
}
