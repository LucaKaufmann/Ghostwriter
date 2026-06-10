<script lang="ts">
	import { api } from '$lib/api/client';
	import type { PodcastChapter } from '$lib/api/types';
	import { Button } from '$lib/components/ui/button';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import { formatPlayerTime } from '$lib/utils/episode';
	import {
		ListOrdered,
		Loader2,
		Pause,
		Play,
		RotateCcw,
		SkipBack,
		SkipForward
	} from 'lucide-svelte';

	interface Props {
		episodeId: string;
		durationHint?: number | null;
		chapters?: PodcastChapter[] | null;
	}

	let { episodeId, durationHint = null, chapters = null }: Props = $props();

	let audioEl: HTMLAudioElement | undefined = $state();
	let blobUrl: string | null = $state(null);
	let loading = $state(false);
	let error: string | null = $state(null);

	let playing = $state(false);
	let currentTime = $state(0);
	let duration = $derived.by(() => audioDuration ?? durationHint ?? 0);
	let audioDuration: number | null = $state(null);
	let playbackRate = $state(1);
	let seeking = $state(false);

	const SPEED_OPTIONS = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];

	async function loadAudio() {
		loading = true;
		error = null;
		try {
			blobUrl = await api.streamPodcastEpisode(episodeId);
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load audio';
		} finally {
			loading = false;
		}
	}

	// Load audio on mount
	$effect(() => {
		// Reference episodeId to re-run when it changes
		void episodeId;
		loadAudio();

		return () => {
			if (blobUrl) {
				URL.revokeObjectURL(blobUrl);
				blobUrl = null;
			}
		};
	});

	function togglePlay() {
		if (!audioEl) return;
		if (playing) {
			audioEl.pause();
		} else {
			audioEl.play();
		}
	}

	function skip(seconds: number) {
		if (!audioEl) return;
		audioEl.currentTime = Math.max(0, Math.min(audioEl.currentTime + seconds, audioEl.duration || 0));
	}

	function handleTimeUpdate() {
		if (!audioEl || seeking) return;
		currentTime = audioEl.currentTime;
	}

	function handleLoadedMetadata() {
		if (!audioEl) return;
		if (audioEl.duration && isFinite(audioEl.duration)) {
			audioDuration = audioEl.duration;
		}
		audioEl.playbackRate = playbackRate;
	}

	function handleDurationChange() {
		if (!audioEl) return;
		if (audioEl.duration && isFinite(audioEl.duration)) {
			audioDuration = audioEl.duration;
		}
	}

	function handleSeekStart() {
		seeking = true;
	}

	function handleSeekInput(e: Event) {
		const target = e.target as HTMLInputElement;
		currentTime = parseFloat(target.value);
	}

	function handleSeekEnd(e: Event) {
		const target = e.target as HTMLInputElement;
		if (audioEl) {
			audioEl.currentTime = parseFloat(target.value);
		}
		seeking = false;
	}

	function setSpeed(speed: number) {
		playbackRate = speed;
		if (audioEl) {
			audioEl.playbackRate = speed;
		}
	}

	function seekToChapter(chapter: PodcastChapter) {
		if (!audioEl) return;
		audioEl.currentTime = chapter.start_seconds;
		currentTime = chapter.start_seconds;
		if (!playing) {
			audioEl.play();
		}
	}

	const progress = $derived(duration > 0 ? (currentTime / duration) * 100 : 0);

	const currentChapterIndex = $derived.by(() => {
		if (!chapters || chapters.length === 0) return -1;
		let index = -1;
		for (let i = 0; i < chapters.length; i++) {
			if (currentTime >= chapters[i].start_seconds) {
				index = i;
			}
		}
		return index;
	});
</script>

<style>
	.seek-bar {
		--progress: 0%;
	}
	.seek-bar::-webkit-slider-runnable-track {
		height: 6px;
		border-radius: 3px;
		background: linear-gradient(
			to right,
			var(--color-primary) var(--progress),
			var(--color-muted) var(--progress)
		);
	}
	.seek-bar::-moz-range-track {
		height: 6px;
		border-radius: 3px;
		background: var(--color-muted);
	}
	.seek-bar::-moz-range-progress {
		height: 6px;
		border-radius: 3px;
		background: var(--color-primary);
	}
	.seek-bar::-webkit-slider-thumb {
		-webkit-appearance: none;
		width: 14px;
		height: 14px;
		border-radius: 50%;
		background: var(--color-primary);
		margin-top: -4px;
		cursor: pointer;
	}
	.seek-bar::-moz-range-thumb {
		width: 14px;
		height: 14px;
		border-radius: 50%;
		background: var(--color-primary);
		border: none;
		cursor: pointer;
	}
</style>

{#if loading}
	<div class="flex items-center justify-center py-8">
		<Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
		<span class="ml-2 text-sm text-muted-foreground">Loading audio...</span>
	</div>
{:else if error}
	<div class="flex flex-col items-center gap-3 py-8">
		<p class="text-sm text-destructive">{error}</p>
		<Button variant="outline" size="sm" onclick={loadAudio}>
			<RotateCcw class="mr-2 h-4 w-4" />
			Retry
		</Button>
	</div>
{:else if blobUrl}
	<audio
		bind:this={audioEl}
		src={blobUrl}
		preload="metadata"
		onplay={() => (playing = true)}
		onpause={() => (playing = false)}
		onended={() => (playing = false)}
		ontimeupdate={handleTimeUpdate}
		onloadedmetadata={handleLoadedMetadata}
		ondurationchange={handleDurationChange}
	></audio>

	<div class="space-y-3">
		<!-- Controls row -->
		<div class="flex items-center justify-between">
			<div class="flex items-center gap-1">
				<Button
					variant="ghost"
					size="sm"
					class="h-9 w-9 p-0"
					onclick={() => skip(-15)}
					aria-label="Skip back 15 seconds"
				>
					<SkipBack class="h-4 w-4" />
				</Button>
				<Button
					variant="ghost"
					size="sm"
					class="h-10 w-10 p-0"
					onclick={togglePlay}
					aria-label={playing ? 'Pause' : 'Play'}
				>
					{#if playing}
						<Pause class="h-5 w-5" />
					{:else}
						<Play class="h-5 w-5" />
					{/if}
				</Button>
				<Button
					variant="ghost"
					size="sm"
					class="h-9 w-9 p-0"
					onclick={() => skip(15)}
					aria-label="Skip forward 15 seconds"
				>
					<SkipForward class="h-4 w-4" />
				</Button>
			</div>

			<!-- Playback speed -->
			<DropdownMenu.Root>
				<DropdownMenu.Trigger>
					{#snippet child({ props })}
						<Button {...props} variant="ghost" size="sm" class="h-8 px-2 text-xs font-mono">
							{playbackRate}x
						</Button>
					{/snippet}
				</DropdownMenu.Trigger>
				<DropdownMenu.Content align="end" class="w-24">
					<DropdownMenu.RadioGroup value={String(playbackRate)}>
						{#each SPEED_OPTIONS as speed}
							<DropdownMenu.RadioItem
								value={String(speed)}
								onclick={() => setSpeed(speed)}
							>
								{speed}x
							</DropdownMenu.RadioItem>
						{/each}
					</DropdownMenu.RadioGroup>
				</DropdownMenu.Content>
			</DropdownMenu.Root>
		</div>

		<!-- Seek bar + time -->
		<div class="flex items-center gap-3">
			<span class="w-12 text-right text-xs tabular-nums text-muted-foreground">
				{formatPlayerTime(currentTime)}
			</span>
			<input
				type="range"
				class="seek-bar h-1.5 w-full cursor-pointer appearance-none bg-transparent"
				style="--progress: {progress}%"
				min="0"
				max={duration || 0}
				step="0.1"
				value={currentTime}
				onmousedown={handleSeekStart}
				ontouchstart={handleSeekStart}
				oninput={handleSeekInput}
				onchange={handleSeekEnd}
				aria-label="Seek"
			/>
			<span class="w-12 text-xs tabular-nums text-muted-foreground">
				{formatPlayerTime(duration)}
			</span>
		</div>

		<!-- Chapters -->
		{#if chapters && chapters.length > 0}
			<div class="space-y-1">
				<p class="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
					<ListOrdered class="h-3.5 w-3.5" />
					Chapters
				</p>
				<ol class="divide-y rounded-md border">
					{#each chapters as chapter, index}
						<li>
							<button
								type="button"
								class="flex w-full items-center gap-3 px-3 py-2 text-left text-sm transition-colors hover:bg-muted {index ===
								currentChapterIndex
									? 'bg-muted font-medium'
									: ''}"
								onclick={() => seekToChapter(chapter)}
							>
								<span class="w-10 shrink-0 text-xs tabular-nums text-muted-foreground">
									{formatPlayerTime(chapter.start_seconds)}
								</span>
								<span class="min-w-0 flex-1 truncate">{chapter.title}</span>
								{#if index === currentChapterIndex && playing}
									<span class="shrink-0 text-xs text-primary">Playing</span>
								{/if}
							</button>
						</li>
					{/each}
				</ol>
			</div>
		{/if}
	</div>
{/if}
