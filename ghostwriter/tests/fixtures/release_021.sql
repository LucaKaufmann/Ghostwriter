-- Synthetic SQLite fixture from ghostwriter-v1.1.0 (43ac1e1b7f3fd23c54c4176e6a1b4a2ca6b1f2fa).
-- Created from the tagged SQLModel metadata; no production rows or credentials.
-- Includes all tagged model tables and seven deterministic synthetic records.
BEGIN TRANSACTION;
CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL);
INSERT INTO "alembic_version" VALUES('021');
CREATE TABLE api_tokens (
	id CHAR(32) NOT NULL, 
	user_id CHAR(32) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	token_hash VARCHAR(255) NOT NULL, 
	token_prefix VARCHAR(16) NOT NULL, 
	created_at DATETIME NOT NULL, 
	last_used_at DATETIME, 
	revoked_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);
CREATE TABLE article_feedback (
	user_id CHAR(32), 
	article_id CHAR(32) NOT NULL, 
	digest_id CHAR(32), 
	rating VARCHAR, 
	read_duration_sec INTEGER, 
	bookmarked BOOLEAN NOT NULL, 
	shared BOOLEAN NOT NULL, 
	id CHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_article_feedback_user_article UNIQUE (user_id, article_id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(digest_id) REFERENCES digests (id)
);
CREATE TABLE client_config (
	min_word_count INTEGER NOT NULL, 
	morning_hour INTEGER NOT NULL, 
	morning_minute INTEGER NOT NULL, 
	noon_hour INTEGER NOT NULL, 
	noon_minute INTEGER NOT NULL, 
	evening_hour INTEGER NOT NULL, 
	evening_minute INTEGER NOT NULL, 
	timezone VARCHAR NOT NULL, 
	newsletters_enabled BOOLEAN NOT NULL, 
	newsletter_mode VARCHAR NOT NULL, 
	whisper_provider VARCHAR NOT NULL, 
	whisper_model VARCHAR NOT NULL, 
	whisper_timeout_minutes INTEGER NOT NULL, 
	media_processing_interval_hours INTEGER NOT NULL, 
	include_podcasts_in_digest BOOLEAN NOT NULL, 
	include_youtube_in_digest BOOLEAN NOT NULL, 
	pdf_enabled BOOLEAN NOT NULL, 
	pdf_page_size VARCHAR NOT NULL, 
	cover_enabled BOOLEAN NOT NULL, 
	cover_provider VARCHAR NOT NULL, 
	cover_quality VARCHAR NOT NULL, 
	cover_prompt VARCHAR NOT NULL, 
	cover_overlay_enabled BOOLEAN NOT NULL, 
	cover_openai_api_key VARCHAR NOT NULL, 
	cover_gemini_api_key VARCHAR NOT NULL, 
	id CHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
INSERT INTO "client_config" VALUES(0,7,0,12,0,18,0,'UTC',1,'summarize','local','base.en',30,4,1,1,0,'A4',0,'gpt-image-1','low','',1,'','','00000000000000000000000000000006','2026-06-07 12:00:00.000000','2026-06-07 12:00:00.000000');
CREATE TABLE client_settings (
	id CHAR(32) NOT NULL, 
	last_heartbeat_at DATETIME, 
	last_download_at DATETIME, 
	last_feed_sync_at DATETIME, 
	auto_disable_enabled BOOLEAN NOT NULL, 
	auto_disable_after_days INTEGER NOT NULL, 
	schedules_auto_disabled BOOLEAN NOT NULL, 
	auto_disabled_at DATETIME, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE digest_articles (
	title VARCHAR NOT NULL, 
	url VARCHAR NOT NULL, 
	mode VARCHAR NOT NULL, 
	word_count INTEGER NOT NULL, 
	ai_failed BOOLEAN NOT NULL, 
	processing_ms INTEGER NOT NULL, 
	content TEXT DEFAULT '' NOT NULL, 
	author VARCHAR, 
	feed_title VARCHAR DEFAULT '' NOT NULL, 
	sort_order INTEGER NOT NULL, 
	content_type VARCHAR DEFAULT 'article' NOT NULL, 
	id CHAR(32) NOT NULL, 
	digest_id CHAR(32) NOT NULL, 
	feed_id CHAR(32) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(digest_id) REFERENCES digests (id), 
	FOREIGN KEY(feed_id) REFERENCES feeds (id)
);
INSERT INTO "digest_articles" VALUES('Synthetic article','https://fixture.example/article','raw',0,0,0,'Synthetic content for restore verification.',NULL,'Fixture feed',0,'article','00000000000000000000000000000003','00000000000000000000000000000002','00000000000000000000000000000001');
CREATE TABLE digests (
	filename VARCHAR NOT NULL, 
	period VARCHAR NOT NULL, 
	status VARCHAR NOT NULL, 
	stage VARCHAR, 
	article_count INTEGER NOT NULL, 
	error_message VARCHAR, 
	id CHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	completed_at DATETIME, 
	downloaded_at DATETIME, 
	locked_at DATETIME, 
	locked_by VARCHAR, 
	total_feeds INTEGER NOT NULL, 
	feeds_fetched INTEGER NOT NULL, 
	total_articles INTEGER NOT NULL, 
	articles_enriched INTEGER NOT NULL, 
	PRIMARY KEY (id)
);
INSERT INTO "digests" VALUES('fixture-edition.epub','manual','completed','completed',1,NULL,'00000000000000000000000000000002','2026-06-07 12:00:00.000000','2026-06-07 12:00:00.000000',NULL,NULL,NULL,0,0,0,0);
CREATE TABLE feeds (
	url VARCHAR NOT NULL, 
	title VARCHAR NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	mode VARCHAR NOT NULL, 
	max_articles INTEGER NOT NULL, 
	deleted_at DATETIME, 
	id CHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
INSERT INTO "feeds" VALUES('https://fixture.example/feed.xml','Fixture feed',1,'raw',0,NULL,'00000000000000000000000000000001','2026-06-07 12:00:00.000000','2026-06-07 12:00:00.000000');
CREATE TABLE manual_covers (
	id CHAR(32) NOT NULL, 
	name VARCHAR NOT NULL, 
	file_name VARCHAR NOT NULL, 
	media_type VARCHAR NOT NULL, 
	size_bytes INTEGER NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE media_feeds (
	feed_type VARCHAR NOT NULL, 
	url VARCHAR NOT NULL, 
	resolved_feed_url VARCHAR, 
	title VARCHAR NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	mode VARCHAR NOT NULL, 
	max_items INTEGER NOT NULL, 
	deleted_at DATETIME, 
	id CHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE media_items (
	id CHAR(32) NOT NULL, 
	media_feed_id CHAR(32) NOT NULL, 
	guid VARCHAR NOT NULL, 
	url VARCHAR NOT NULL, 
	content_url VARCHAR, 
	title VARCHAR NOT NULL, 
	author VARCHAR, 
	content TEXT DEFAULT '' NOT NULL, 
	content_type VARCHAR DEFAULT 'podcast' NOT NULL, 
	mode VARCHAR DEFAULT 'raw' NOT NULL, 
	word_count INTEGER NOT NULL, 
	is_summary BOOLEAN NOT NULL, 
	ai_failed BOOLEAN NOT NULL, 
	processing_ms INTEGER NOT NULL, 
	status VARCHAR DEFAULT 'pending' NOT NULL, 
	error_message VARCHAR, 
	consumed_at DATETIME, 
	consumed_digest_id CHAR(32), 
	created_at DATETIME NOT NULL, 
	completed_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(media_feed_id) REFERENCES media_feeds (id)
);
CREATE TABLE media_processing_runs (
	id CHAR(32) NOT NULL, 
	started_at DATETIME NOT NULL, 
	completed_at DATETIME, 
	duration_ms INTEGER NOT NULL, 
	status VARCHAR DEFAULT 'running' NOT NULL, 
	items_discovered INTEGER NOT NULL, 
	items_processed INTEGER NOT NULL, 
	items_failed INTEGER NOT NULL, 
	error_message TEXT, 
	PRIMARY KEY (id)
);
CREATE TABLE podcast_episode_counters (
	owner_key VARCHAR NOT NULL, 
	next_episode_number INTEGER NOT NULL, 
	PRIMARY KEY (owner_key)
);
CREATE TABLE podcast_episodes (
	digest_ids JSON DEFAULT '[]' NOT NULL, 
	"trigger" VARCHAR DEFAULT 'manual' NOT NULL, 
	user_id CHAR(32), 
	script TEXT, 
	audio_path VARCHAR, 
	audio_size_bytes INTEGER, 
	duration_seconds INTEGER, 
	episode_number INTEGER, 
	article_ids JSON DEFAULT '[]' NOT NULL, 
	article_count INTEGER NOT NULL, 
	generation_cost_cents INTEGER, 
	status VARCHAR DEFAULT 'pending' NOT NULL, 
	error_message VARCHAR, 
	id CHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	started_at DATETIME, 
	completed_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);
INSERT INTO "podcast_episodes" VALUES('["00000000-0000-0000-0000-000000000002"]','manual',NULL,'Synthetic script','/app/output/podcasts/00000000-0000-0000-0000-000000000004.mp3',18,NULL,1,'["00000000-0000-0000-0000-000000000003"]',0,NULL,'ready',NULL,'00000000000000000000000000000004','2026-06-07 12:00:00.000000','2026-06-07 12:00:00.000000',NULL,'2026-06-07 12:00:00.000000');
CREATE TABLE podcast_preferences (
	user_id CHAR(32), 
	enabled BOOLEAN NOT NULL, 
	schedule VARCHAR DEFAULT 'manual' NOT NULL, 
	schedule_time VARCHAR NOT NULL, 
	schedule_day VARCHAR DEFAULT 'monday' NOT NULL, 
	topic_weights JSON DEFAULT '{}' NOT NULL, 
	boost_sources JSON DEFAULT '[]' NOT NULL, 
	boost_keywords JSON DEFAULT '[]' NOT NULL, 
	filter_keywords JSON DEFAULT '[]' NOT NULL, 
	preferred_length_minutes INTEGER NOT NULL, 
	script_model VARCHAR, 
	script_timeout_seconds INTEGER NOT NULL, 
	style VARCHAR DEFAULT 'casual' NOT NULL, 
	tts_provider VARCHAR DEFAULT 'openai' NOT NULL, 
	openai_tts_model VARCHAR NOT NULL, 
	openai_api_key VARCHAR, 
	elevenlabs_model_id VARCHAR NOT NULL, 
	elevenlabs_api_key VARCHAR, 
	elevenlabs_output_format VARCHAR NOT NULL, 
	host_a_voice VARCHAR NOT NULL, 
	host_b_voice VARCHAR NOT NULL, 
	host_count INTEGER NOT NULL, 
	podcast_feed_enabled BOOLEAN NOT NULL, 
	podcast_feed_title VARCHAR NOT NULL, 
	podcast_feed_description VARCHAR NOT NULL, 
	podcast_feed_base_url VARCHAR, 
	podcast_feed_artwork_path VARCHAR, 
	podcast_feed_token VARCHAR NOT NULL, 
	id CHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);
INSERT INTO "podcast_preferences" VALUES(NULL,0,'manual','08:00','monday','{}','[]','[]','[]',20,NULL,60,'formal','openai','tts-1',NULL,'eleven_turbo_v2_5',NULL,'mp3_44100_128','alloy','echo',2,0,'My Ghostwriter Digest','AI-generated audio digest of your RSS feeds',NULL,NULL,'','00000000000000000000000000000007','2026-06-07 12:00:00.000000','2026-06-07 12:00:00.000000');
CREATE TABLE podcast_schedules (
	user_id CHAR(32), 
	name VARCHAR(100) NOT NULL, 
	days JSON DEFAULT '[]' NOT NULL, 
	time VARCHAR(5) NOT NULL, 
	timezone VARCHAR DEFAULT 'UTC' NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	last_run_at DATETIME, 
	last_episode_id CHAR(32), 
	id CHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);
CREATE TABLE schedules (
	period VARCHAR NOT NULL, 
	hour INTEGER NOT NULL, 
	minute INTEGER NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	timezone VARCHAR NOT NULL, 
	id CHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	last_run_at DATETIME, 
	last_run_digest_id CHAR(32), 
	PRIMARY KEY (id)
);
CREATE TABLE seen_articles (
	id CHAR(32) NOT NULL, 
	feed_id CHAR(32), 
	guid VARCHAR NOT NULL, 
	url VARCHAR NOT NULL, 
	title VARCHAR NOT NULL, 
	seen_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(feed_id) REFERENCES feeds (id)
);
INSERT INTO "seen_articles" VALUES('00000000000000000000000000000005','00000000000000000000000000000001','fixture-guid','https://fixture.example/article','Synthetic article','2026-06-07 12:00:00.000000');
CREATE TABLE users (
	id CHAR(32) NOT NULL, 
	username VARCHAR(50) NOT NULL, 
	email VARCHAR(254), 
	password_hash VARCHAR(255) NOT NULL, 
	is_admin BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	last_login_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE wallabag_config (
	id CHAR(32) NOT NULL, 
	url VARCHAR NOT NULL, 
	client_id VARCHAR NOT NULL, 
	client_secret VARCHAR NOT NULL, 
	username VARCHAR NOT NULL, 
	password VARCHAR NOT NULL, 
	mode VARCHAR NOT NULL, 
	max_articles INTEGER NOT NULL, 
	tag_on_process VARCHAR NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_digests_status ON digests (status);
CREATE UNIQUE INDEX ix_feeds_url ON feeds (url);
CREATE UNIQUE INDEX ix_media_feeds_url ON media_feeds (url);
CREATE UNIQUE INDEX ix_users_username ON users (username);
CREATE INDEX ix_article_feedback_created_at ON article_feedback (created_at);
CREATE INDEX ix_article_feedback_digest_id ON article_feedback (digest_id);
CREATE INDEX ix_article_feedback_article_id ON article_feedback (article_id);
CREATE INDEX ix_article_feedback_user_id ON article_feedback (user_id);
CREATE INDEX ix_api_tokens_user_id ON api_tokens (user_id);
CREATE INDEX ix_digest_articles_feed_id ON digest_articles (feed_id);
CREATE INDEX ix_digest_articles_digest_id ON digest_articles (digest_id);
CREATE INDEX ix_media_items_status ON media_items (status);
CREATE INDEX ix_media_items_guid ON media_items (guid);
CREATE INDEX ix_media_items_feed_id ON media_items (media_feed_id);
CREATE INDEX ix_podcast_episodes_user_id ON podcast_episodes (user_id);
CREATE INDEX ix_podcast_episodes_status ON podcast_episodes (status);
CREATE INDEX ix_podcast_preferences_user_id ON podcast_preferences (user_id);
CREATE INDEX ix_podcast_schedules_user_id ON podcast_schedules (user_id);
CREATE INDEX ix_seen_articles_feed_id ON seen_articles (feed_id);
CREATE INDEX ix_seen_articles_guid ON seen_articles (guid);
CREATE INDEX ix_seen_articles_feed_guid ON seen_articles (feed_id, guid);
COMMIT;
