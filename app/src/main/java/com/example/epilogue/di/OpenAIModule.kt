package com.example.epilogue.di

import com.example.epilogue.data.remote.openai.OpenAIApi
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object OpenAIModule {

    @Provides
    @Singleton
    fun provideOpenAIApi(okHttpClient: OkHttpClient): OpenAIApi {
        return Retrofit.Builder()
            .baseUrl(OpenAIApi.BASE_URL)
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(OpenAIApi::class.java)
    }
}
