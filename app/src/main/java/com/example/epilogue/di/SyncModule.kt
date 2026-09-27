package com.example.epilogue.di

import com.example.epilogue.shared.sync.ConfigSyncUseCase
import com.example.epilogue.shared.sync.DigestStorePort
import com.example.epilogue.shared.sync.DigestSyncUseCase
import com.example.epilogue.shared.sync.FeedStorePort
import com.example.epilogue.shared.sync.FeedSyncV2UseCase
import com.example.epilogue.shared.sync.FeedV2ConfigurationPort
import com.example.epilogue.shared.sync.FeedV2RemotePort
import com.example.epilogue.shared.sync.FeedV2StorePort
import com.example.epilogue.shared.sync.GhostwriterSyncPort
import com.example.epilogue.shared.sync.SettingsPort
import com.example.epilogue.sync.AndroidDigestStorePort
import com.example.epilogue.sync.AndroidFeedStorePort
import com.example.epilogue.sync.AndroidGhostwriterSyncPort
import com.example.epilogue.sync.AndroidSettingsPort
import com.example.epilogue.sync.AndroidFeedV2RemotePort
import com.example.epilogue.data.repository.AndroidFeedV2Store
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object SyncModule {
    @Provides @Singleton
    fun provideFeedV2StorePort(impl: AndroidFeedV2Store): FeedV2StorePort = impl

    @Provides @Singleton
    fun provideFeedV2ConfigurationPort(impl: AndroidFeedV2Store): FeedV2ConfigurationPort = impl

    @Provides @Singleton
    fun provideFeedV2RemotePort(impl: AndroidFeedV2RemotePort): FeedV2RemotePort = impl

    @Provides @Singleton
    fun provideFeedSyncV2UseCase(configuration: FeedV2ConfigurationPort, store: FeedV2StorePort,
        remote: FeedV2RemotePort): FeedSyncV2UseCase = FeedSyncV2UseCase(configuration, store, remote)
    @Provides
    @Singleton
    fun provideSettingsPort(impl: AndroidSettingsPort): SettingsPort = impl

    @Provides
    @Singleton
    fun provideFeedStorePort(impl: AndroidFeedStorePort): FeedStorePort = impl

    @Provides
    @Singleton
    fun provideDigestStorePort(impl: AndroidDigestStorePort): DigestStorePort = impl

    @Provides
    @Singleton
    fun provideGhostwriterSyncPort(impl: AndroidGhostwriterSyncPort): GhostwriterSyncPort = impl

    @Provides
    @Singleton
    fun provideConfigSyncUseCase(
        settings: SettingsPort,
        ghostwriter: GhostwriterSyncPort
    ): ConfigSyncUseCase = ConfigSyncUseCase(settings, ghostwriter)

    @Provides
    @Singleton
    fun provideDigestSyncUseCase(
        settings: SettingsPort,
        digestStore: DigestStorePort,
        ghostwriter: GhostwriterSyncPort
    ): DigestSyncUseCase = DigestSyncUseCase(settings, digestStore, ghostwriter)
}
