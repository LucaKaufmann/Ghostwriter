<script lang="ts">
	import { page } from '$app/stores';
	import { createQuery, createMutation, useQueryClient } from '@tanstack/svelte-query';
	import { api } from '$lib/api/client';
	import type { PodcastEpisodeDetailResponse } from '$lib/api/types';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { formatUTCDate } from '$lib/utils/date';
	import {
		getEpisodeStatusBadgeVariant,
		getEpisodeStatusLabel,
		isEpisodeActive,
		formatDuration,
		formatCost
	} from '$lib/utils/episode';
	import { AudioPlayer } from '$lib/components/ui/audio-player';
	import {
		ArrowLeft,
		Calendar,
		Clock,
		Download,
		ExternalLink,
		FileText,
		Loader2,
		Mic,
		RotateCcw,
		Trash2
	} from 'lucide-svelte';
	import { toast } from 'svelte-sonner';
	import { goto } from '$app/navigation';

	const queryClient = useQueryClient();
	const episodeId = $derived($page.params.id);

	const episodeQuery = createQuery(() => ({
		queryKey: ['podcast-episode', episodeId],
		queryFn: () => api.getPodcastEpisode(episodeId!),
		enabled: !!episodeId,
		refetchInterval: (query) => {
			const ep = query.state.data;
			return ep && isEpisodeActive(ep.status) ? 5000 : false;
		}
	}));

	const retryMutation = createMutation(() => ({
		mutationFn: () => api.retryPodcastEpisode(episodeId!),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['podcast-episode', episodeId] });
			queryClient.invalidateQueries({ queryKey: ['podcast-episodes'] });
			toast.success('Episode retry queued');
		},
		onError: (err: Error) => {
			toast.error('Failed to retry episode', { description: err.message });
		}
	}));

	const deleteMutation = createMutation(() => ({
		mutationFn: () => api.deletePodcastEpisode(episodeId!),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['podcast-episodes'] });
			toast.success('Episode deleted');
			goto('/episodes');
		},
		onError: (err: Error) => {
			toast.error('Failed to delete episode', { description: err.message });
		}
	}));

	let downloadPending = $state(false);

	const CHAPTER_LINE = /^\[CHAPTER\]:\s*(.+)$/i;

	type ScriptBlock = { kind: 'chapter' | 'text'; content: string };

	function scriptBlocks(script: string): ScriptBlock[] {
		const blocks: ScriptBlock[] = [];
		for (const line of script.split('\n')) {
			const chapterMatch = line.trim().match(CHAPTER_LINE);
			if (chapterMatch) {
				blocks.push({ kind: 'chapter', content: chapterMatch[1] });
			} else if (blocks.length > 0 && blocks[blocks.length - 1].kind === 'text') {
				blocks[blocks.length - 1].content += '\n' + line;
			} else {
				blocks.push({ kind: 'text', content: line });
			}
		}
		return blocks;
	}

	function formatDate(dateStr: string): string {
		return formatUTCDate(dateStr, {
			weekday: 'long',
			year: 'numeric',
			month: 'long',
			day: 'numeric',
			hour: 'numeric',
			minute: '2-digit'
		});
	}

	async function handleDownload(episode: PodcastEpisodeDetailResponse) {
		if (!episode.download_url) return;
		downloadPending = true;
		try {
			const { blob, filename } = await api.downloadPodcastEpisode(episode.id);
			const objectUrl = URL.createObjectURL(blob);
			const anchor = document.createElement('a');
			anchor.href = objectUrl;
			anchor.download = filename;
			document.body.appendChild(anchor);
			anchor.click();
			document.body.removeChild(anchor);
			URL.revokeObjectURL(objectUrl);
		} catch (err) {
			const message = err instanceof Error ? err.message : 'Unknown error';
			toast.error('Failed to download episode', { description: message });
		} finally {
			downloadPending = false;
		}
	}
</script>

<svelte:head>
	<title>Episode Detail - Ghostwriter</title>
</svelte:head>

<div class="space-y-6">
	<div>
		<a href="/episodes" class="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
			<ArrowLeft class="h-4 w-4" />
			Back to Episodes
		</a>
	</div>

	{#if episodeQuery.isPending}
		<div class="space-y-4">
			<Skeleton class="h-8 w-64" />
			<Skeleton class="h-48 w-full" />
			<Skeleton class="h-64 w-full" />
		</div>
	{:else if episodeQuery.isError}
		<Card.Root>
			<Card.Content class="py-12 text-center">
				<p class="text-lg font-medium">Failed to load episode</p>
				<p class="text-sm text-muted-foreground">{episodeQuery.error?.message}</p>
				<Button class="mt-4" variant="outline" onclick={() => episodeQuery.refetch()}>
					Try again
				</Button>
			</Card.Content>
		</Card.Root>
	{:else if episodeQuery.data}
		{@const episode = episodeQuery.data}

		<!-- Header -->
		<div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
			<div>
				<h1 class="flex items-center gap-2 text-2xl font-bold tracking-tight">
					<Mic class="h-6 w-6" />
					<span class="capitalize">{episode.trigger}</span> Episode
				</h1>
				<p class="text-muted-foreground">{formatDate(episode.created_at)}</p>
			</div>
			<Badge variant={getEpisodeStatusBadgeVariant(episode.status)} class="w-fit">
				{#if isEpisodeActive(episode.status)}
					<Loader2 class="mr-1 h-3 w-3 animate-spin" />
				{/if}
				{getEpisodeStatusLabel(episode.status)}
			</Badge>
		</div>

		<!-- Metadata -->
		<Card.Root>
			<Card.Header>
				<Card.Title class="text-base">Details</Card.Title>
			</Card.Header>
			<Card.Content>
				<dl class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
					<div>
						<dt class="text-sm font-medium text-muted-foreground">Trigger</dt>
						<dd class="capitalize">{episode.trigger}</dd>
					</div>
					<div>
						<dt class="text-sm font-medium text-muted-foreground">Articles</dt>
						<dd>{episode.article_count}</dd>
					</div>
					{#if episode.duration_seconds}
						<div>
							<dt class="text-sm font-medium text-muted-foreground">Duration</dt>
							<dd class="flex items-center gap-1">
								<Clock class="h-4 w-4 text-muted-foreground" />
								{formatDuration(episode.duration_seconds)}
							</dd>
						</div>
					{/if}
					{#if episode.generation_cost_cents}
						<div>
							<dt class="text-sm font-medium text-muted-foreground">Cost</dt>
							<dd>{formatCost(episode.generation_cost_cents)}</dd>
						</div>
					{/if}
					<div>
						<dt class="text-sm font-medium text-muted-foreground">Created</dt>
						<dd class="flex items-center gap-1">
							<Calendar class="h-4 w-4 text-muted-foreground" />
							{formatDate(episode.created_at)}
						</dd>
					</div>
					{#if episode.completed_at}
						<div>
							<dt class="text-sm font-medium text-muted-foreground">Completed</dt>
							<dd>{formatDate(episode.completed_at)}</dd>
						</div>
					{/if}
				</dl>
				{#if episode.error_message}
					<div class="mt-4 rounded-md border border-destructive/50 bg-destructive/10 p-3">
						<p class="text-sm font-medium text-destructive">Error</p>
						<p class="text-sm text-destructive/80">{episode.error_message}</p>
					</div>
				{/if}
			</Card.Content>
		</Card.Root>

		<!-- Audio Player & Actions -->
		{#if episode.status === 'ready' && episode.stream_url}
			<Card.Root>
				<Card.Header>
					<Card.Title class="text-base">Audio</Card.Title>
				</Card.Header>
				<Card.Content class="space-y-4">
					<AudioPlayer
						episodeId={episode.id}
						durationHint={episode.duration_seconds}
						chapters={episode.chapters}
					/>
					<div class="flex items-center gap-2">
						<Button variant="outline" onclick={() => handleDownload(episode)} disabled={downloadPending}>
							{#if downloadPending}
								<Loader2 class="mr-2 h-4 w-4 animate-spin" />
								Preparing...
							{:else}
								<Download class="mr-2 h-4 w-4" />
								Download MP3
							{/if}
						</Button>
					</div>
				</Card.Content>
			</Card.Root>
		{/if}

		<!-- Script -->
		{#if episode.script}
			<Card.Root>
				<Card.Header>
					<Card.Title class="flex items-center gap-2 text-base">
						<FileText class="h-4 w-4" />
						Script
					</Card.Title>
				</Card.Header>
				<Card.Content>
					<div class="prose prose-sm dark:prose-invert max-w-none">
						{#each scriptBlocks(episode.script) as block}
							{#if block.kind === 'chapter'}
								<h3 class="mt-4 mb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground first:mt-0">
									{block.content}
								</h3>
							{:else}
								<div class="whitespace-pre-wrap">{block.content}</div>
							{/if}
						{/each}
					</div>
				</Card.Content>
			</Card.Root>
		{/if}

		<!-- Source Articles -->
		{#if episode.articles.length > 0}
			<Card.Root>
				<Card.Header>
					<Card.Title class="text-base">Source Articles ({episode.articles.length})</Card.Title>
				</Card.Header>
				<Card.Content class="p-0">
					<div class="divide-y">
						{#each episode.articles as article}
							<div class="flex items-center justify-between gap-4 px-6 py-3">
								<div class="min-w-0 flex-1">
									<p class="truncate font-medium">{article.title}</p>
									<p class="text-sm text-muted-foreground">{article.feed_title}</p>
								</div>
								{#if article.url}
									<a href={article.url} target="_blank" rel="noopener noreferrer">
										<Button size="sm" variant="ghost">
											<ExternalLink class="h-4 w-4" />
										</Button>
									</a>
								{/if}
							</div>
						{/each}
					</div>
				</Card.Content>
			</Card.Root>
		{/if}

		<!-- Actions -->
		<div class="flex items-center gap-2">
			{#if episode.status === 'failed'}
				<Button variant="outline" onclick={() => retryMutation.mutate()} disabled={retryMutation.isPending}>
					{#if retryMutation.isPending}
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
						Retrying...
					{:else}
						<RotateCcw class="mr-2 h-4 w-4" />
						Retry
					{/if}
				</Button>
			{/if}
			<Button
				variant="outline"
				class="text-destructive hover:text-destructive"
				onclick={() => deleteMutation.mutate()}
				disabled={deleteMutation.isPending}
			>
				{#if deleteMutation.isPending}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
				{/if}
				<Trash2 class="mr-2 h-4 w-4" />
				Delete Episode
			</Button>
		</div>
	{/if}
</div>
