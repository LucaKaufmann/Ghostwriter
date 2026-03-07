package com.example.epilogue.di

import com.example.epilogue.shared.sync.ConfigSyncUseCase
import com.example.epilogue.shared.sync.DigestStorePort
import com.example.epilogue.shared.sync.DigestSyncUseCase
import com.example.epilogue.shared.sync.FeedStorePort
import com.example.epilogue.shared.sync.FeedSyncUseCase
import com.example.epilogue.shared.sync.GhostwriterSyncPort
import com.example.epilogue.shared.sync.SettingsPort
import com.example.epilogue.sync.AndroidDigestStorePort
import com.example.epilogue.sync.AndroidFeedStorePort
import com.example.epilogue.sync.AndroidGhostwriterSyncPort
import com.example.epilogue.sync.AndroidSettingsPort
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object SyncModule {
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
    fun provideFeedSyncUseCase(
        settings: SettingsPort,
        feedStore: FeedStorePort,
        ghostwriter: GhostwriterSyncPort
    ): FeedSyncUseCase = FeedSyncUseCase(settings, feedStore, ghostwriter)

    @Provides
    @Singleton
    fun provideDigestSyncUseCase(
        settings: SettingsPort,
        digestStore: DigestStorePort,
        ghostwriter: GhostwriterSyncPort
    ): DigestSyncUseCase = DigestSyncUseCase(settings, digestStore, ghostwriter)
}
