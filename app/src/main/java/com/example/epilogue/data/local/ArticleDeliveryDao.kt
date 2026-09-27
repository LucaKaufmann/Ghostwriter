package com.example.epilogue.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Dao
interface ArticleDeliveryDao {
    @Query("SELECT * FROM article_delivery WHERE feedUrl = :feedUrl AND articleKey = :articleKey")
    suspend fun get(feedUrl: String, articleKey: String): ArticleDeliveryEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun put(row: ArticleDeliveryEntity)

    @Query("SELECT * FROM article_delivery WHERE feedUrl = :feedUrl")
    suspend fun forFeed(feedUrl: String): List<ArticleDeliveryEntity>
}
