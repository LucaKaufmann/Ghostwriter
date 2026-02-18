<script lang="ts">
	import { createQuery, createMutation, useQueryClient } from '@tanstack/svelte-query';
	import { api } from '$lib/api/client';
	import type { MediaFeed, MediaFeedCreate, MediaFeedUpdate, MediaProcessingRun } from '$lib/api/types';
	import * as Card from '$lib/components/ui/card';
	import * as Table from '$lib/components/ui/table';
	import * as Dialog from '$lib/components/ui/dialog';
	import * as AlertDialog from '$lib/components/ui/alert-dialog';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Badge } from '$lib/components/ui/badge';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import * as Select from '$lib/components/ui/select';
	import { Switch } from '$lib/components/ui/switch';
	import { toast } from 'svelte-sonner';
	import {
		Plus,
		Trash2,
		Pencil,
		Search,
		Headphones,
		ExternalLink,
		MoreHorizontal,
		Loader2,
		FileText,
		Clock,
		AlertCircle,
		ChevronDown,
		Timer,
		Settings,
		RotateCcw
	} from 'lucide-svelte';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';

	const queryClient = useQueryClient();

	// Queries
	const feedsQuery = createQuery(() => ({
		queryKey: ['podcast-feeds'],
		queryFn: () => api.getPodcastFeeds()
	}));

	const mediaStatusQuery = createQuery(() => ({
		queryKey: ['media-status'],
		queryFn: () => api.getMediaProcessingStatus(),
		refetchInterval: (query) => query.state.data?.is_running ? 5000 : false
	}));

	const itemsQuery = createQuery(() => ({
		queryKey: ['podcast-items'],
		queryFn: () => api.getAllPodcastItems(),
		refetchInterval: mediaStatusQuery.data?.is_running ? 5000 : false
	}));

	const runsQuery = createQuery(() => ({
		queryKey: ['media-runs'],
		queryFn: () => api.getMediaRuns(5)
	}));

	// Mutations
	const createFeedMutation = createMutation(() => ({
		mutationFn: (data: MediaFeedCreate) => api.createPodcastFeed(data),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['podcast-feeds'] });
			toast.success('Podcast feed created');
			addDialogOpen = false;
			resetForm();
		},
		onError: (err: Error) => {
			toast.error('Failed to create podcast feed', { description: err.message });
		}
	}));

	const deleteFeedMutation = createMutation(() => ({
		mutationFn: (id: string) => api.deletePodcastFeed(id),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['podcast-feeds'] });
			toast.success('Podcast feed deleted');
			feedToDelete = null;
		},
		onError: (err: Error) => {
			toast.error('Failed to delete feed', { description: err.message });
		}
	}));

	const updateFeedMutation = createMutation(() => ({
		mutationFn: ({ id, data }: { id: string; data: MediaFeedUpdate }) =>
			api.updatePodcastFeed(id, data),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['podcast-feeds'] });
			toast.success('Podcast feed updated');
			editDialogOpen = false;
			feedToEdit = null;
		},
		onError: (err: Error) => {
			toast.error('Failed to update feed', { description: err.message });
		}
	}));

	const toggleFeedMutation = createMutation(() => ({
		mutationFn: ({ id, data }: { id: string; data: MediaFeedUpdate }) =>
			api.updatePodcastFeed(id, data),
		onSuccess: (_data: MediaFeed, variables: { id: string; data: MediaFeedUpdate }) => {
			queryClient.invalidateQueries({ queryKey: ['podcast-feeds'] });
			toast.success(variables.data.is_active ? 'Feed activated' : 'Feed paused');
		},
		onError: (err: Error) => {
			toast.error('Failed to update feed status', { description: err.message });
		},
		onSettled: () => {
			updatingFeedId = null;
		}
	}));

	const retryItemMutation = createMutation(() => ({
		mutationFn: (itemId: string) => api.retryMediaItem(itemId),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['podcast-items'] });
			queryClient.invalidateQueries({ queryKey: ['media-status'] });
			queryClient.invalidateQueries({ queryKey: ['media-runs'] });
			toast.success('Transcript queued for next media processing run');
		},
		onError: (err: Error) => {
			toast.error('Failed to queue transcript retry', { description: err.message });
		},
		onSettled: () => {
			retryingItemId = null;
		}
	}));

	const retryAllFailedMutation = createMutation(() => ({
		mutationFn: () => api.retryFailedMediaItems('podcast'),
		onSuccess: (result) => {
			queryClient.invalidateQueries({ queryKey: ['podcast-items'] });
			queryClient.invalidateQueries({ queryKey: ['media-status'] });
			queryClient.invalidateQueries({ queryKey: ['media-runs'] });
			toast.success(
				result.retried > 0
					? `${result.retried} failed transcript${result.retried === 1 ? '' : 's'} queued for next run`
					: 'No failed transcripts to queue'
			);
		},
		onError: (err: Error) => {
			toast.error('Failed to queue retries', { description: err.message });
		}
	}));

	// State
	let searchQuery = $state('');
	let addDialogOpen = $state(false);
	let editDialogOpen = $state(false);
	let feedToDelete = $state<MediaFeed | null>(null);
	let feedToEdit = $state<MediaFeed | null>(null);
	let updatingFeedId = $state<string | null>(null);
	let activeTab = $state<'feeds' | 'items'>('feeds');
	let runsExpanded = $state(false);
	let retryingItemId = $state<string | null>(null);

	// Form state
	let formUrl = $state('');
	let formTitle = $state('');
	let formMode = $state<'raw' | 'summarize'>('raw');
	let formMaxItems = $state(5);

	// Edit form state
	let editTitle = $state('');
	let editMode = $state<'raw' | 'summarize'>('raw');
	let editMaxItems = $state(5);
	let editIsActive = $state(true);

	const processingItems = $derived((itemsQuery.data ?? []).filter((i) => i.status === 'processing'));
	const pendingItems = $derived((itemsQuery.data ?? []).filter((i) => i.status === 'pending'));
	const failedItems = $derived((itemsQuery.data ?? []).filter((i) => i.status === 'failed'));
	const completedItems = $derived((itemsQuery.data ?? []).filter((i) => i.status === 'completed'));

	const filteredFeeds = $derived.by(() => {
		const feeds = feedsQuery.data ?? [];
		if (!searchQuery.trim()) return feeds;
		const q = searchQuery.toLowerCase();
		return feeds.filter(
			(f) => f.title.toLowerCase().includes(q) || f.url.toLowerCase().includes(q)
		);
	});

	function resetForm() {
		formUrl = '';
		formTitle = '';
		formMode = 'raw';
		formMaxItems = 5;
	}

	function handleAddFeed(e: Event) {
		e.preventDefault();
		createFeedMutation.mutate({
			feed_type: 'podcast',
			url: formUrl,
			title: formTitle || formUrl,
			mode: formMode,
			max_items: formMaxItems,
			is_active: true
		});
	}

	function handleEditFeed(feed: MediaFeed) {
		feedToEdit = feed;
		editTitle = feed.title;
		editMode = feed.mode as 'raw' | 'summarize';
		editMaxItems = feed.max_items;
		editIsActive = feed.is_active;
		editDialogOpen = true;
	}

	function handleUpdateFeed(e: Event) {
		e.preventDefault();
		if (!feedToEdit) return;
		updateFeedMutation.mutate({
			id: feedToEdit.id,
			data: { title: editTitle, mode: editMode, max_items: editMaxItems, is_active: editIsActive }
		});
	}

	function handleToggleFeed(feed: MediaFeed) {
		if (toggleFeedMutation.isPending) return;
		updatingFeedId = feed.id;
		toggleFeedMutation.mutate({ id: feed.id, data: { is_active: !feed.is_active } });
	}

	function confirmDelete() {
		if (feedToDelete) deleteFeedMutation.mutate(feedToDelete.id);
	}

	function handleRetryItem(itemId: string) {
		if (retryItemMutation.isPending || retryAllFailedMutation.isPending) return;
		retryingItemId = itemId;
		retryItemMutation.mutate(itemId);
	}

	function handleRetryAllFailed() {
		if (retryAllFailedMutation.isPending || retryItemMutation.isPending) return;
		retryAllFailedMutation.mutate();
	}

	function parseUTC(dateStr: string): Date {
		if (!dateStr.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(dateStr)) {
			return new Date(dateStr + 'Z');
		}
		return new Date(dateStr);
	}

	function formatDate(dateStr: string): string {
		return parseUTC(dateStr).toLocaleDateString('en-US', {
			month: 'short',
			day: 'numeric',
			year: 'numeric'
		});
	}

	function formatDuration(ms: number): string {
		if (ms < 1000) return `${ms}ms`;
		const seconds = Math.round(ms / 1000);
		if (seconds < 60) return `${seconds}s`;
		const minutes = Math.floor(seconds / 60);
		const secs = seconds % 60;
		return `${minutes}m ${secs}s`;
	}

	function formatDateTime(dateStr: string): string {
		return parseUTC(dateStr).toLocaleString('en-US', {
			month: 'short',
			day: 'numeric',
			hour: 'numeric',
			minute: '2-digit'
		});
	}
</script>

<svelte:head>
	<title>Podcasts - Ghostwriter</title>
</svelte:head>

<div class="space-y-6 min-w-0">
	<div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
		<div>
			<h1 class="text-2xl font-bold tracking-tight">Podcasts</h1>
			<p class="text-muted-foreground">Manage podcast feeds and view transcriptions</p>
		</div>
		<Button onclick={() => (addDialogOpen = true)}>
			<Plus class="mr-2 h-4 w-4" />
			Add Podcast
		</Button>
	</div>

	<!-- Tabs -->
	<div class="flex gap-2 border-b">
		<button
			class="px-4 py-2 text-sm font-medium border-b-2 transition-colors {activeTab === 'feeds'
				? 'border-primary text-foreground'
				: 'border-transparent text-muted-foreground hover:text-foreground'}"
			onclick={() => (activeTab = 'feeds')}
		>
			Feeds ({feedsQuery.data?.length ?? 0})
		</button>
		<button
			class="px-4 py-2 text-sm font-medium border-b-2 transition-colors {activeTab === 'items'
				? 'border-primary text-foreground'
				: 'border-transparent text-muted-foreground hover:text-foreground'}"
			onclick={() => (activeTab = 'items')}
		>
			Transcripts ({completedItems.length})
		</button>
	</div>

	<!-- Recent Runs -->
	{#if runsQuery.data?.length}
		<div class="rounded-lg border">
			<button
				type="button"
				class="flex w-full items-center justify-between p-3 text-sm font-medium hover:bg-accent/50 transition-colors"
				onclick={() => (runsExpanded = !runsExpanded)}
			>
				<span>Recent Runs</span>
				<ChevronDown class="h-4 w-4 transition-transform {runsExpanded ? 'rotate-180' : ''}" />
			</button>
			{#if runsExpanded}
				<div class="border-t divide-y">
					{#each runsQuery.data as run}
						<div class="px-3 py-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
							<span class="text-muted-foreground">{formatDateTime(run.started_at)}</span>
							<Badge
								variant={run.status === 'completed' ? 'secondary' : run.status === 'running' ? 'default' : 'destructive'}
								class="text-xs"
							>
								{run.status}
							</Badge>
							{#if run.duration_ms > 0}
								<span class="inline-flex items-center gap-1 text-muted-foreground">
									<Timer class="h-3 w-3" />
									{formatDuration(run.duration_ms)}
								</span>
							{/if}
							{#if run.items_discovered > 0 || run.items_processed > 0}
								<span class="text-muted-foreground">
									{run.items_processed} processed{run.items_failed > 0 ? `, ${run.items_failed} failed` : ''}
								</span>
							{/if}
							{#if run.error_message}
								<span class="text-destructive basis-full">{run.error_message}</span>
							{/if}
						</div>
					{/each}
				</div>
			{/if}
		</div>
	{/if}

	{#if activeTab === 'feeds'}
		<!-- Search -->
		<Card.Root>
			<Card.Content class="pt-6">
				<div class="relative">
					<Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
					<Input placeholder="Search podcast feeds..." bind:value={searchQuery} class="pl-9" />
				</div>
			</Card.Content>
		</Card.Root>

		<!-- Feed List -->
		<Card.Root>
			<Card.Content class="p-0">
				{#if feedsQuery.isPending}
					<div class="p-4 space-y-3">
						{#each [1, 2, 3] as _}
							<div class="flex items-center gap-4">
								<Skeleton class="h-10 w-10 rounded" />
								<div class="flex-1 space-y-2">
									<Skeleton class="h-4 w-48" />
									<Skeleton class="h-3 w-64" />
								</div>
							</div>
						{/each}
					</div>
				{:else if !filteredFeeds.length}
					<div class="flex flex-col items-center justify-center py-12 text-center">
						<Headphones class="h-12 w-12 text-muted-foreground/50" />
						<p class="mt-4 text-lg font-medium">
							{searchQuery ? 'No feeds match your search' : 'No podcast feeds yet'}
						</p>
						<p class="text-sm text-muted-foreground">
							{searchQuery ? 'Try a different search term' : 'Add a podcast RSS feed to get started'}
						</p>
						{#if !searchQuery}
							<Button onclick={() => (addDialogOpen = true)} class="mt-4">
								<Plus class="mr-2 h-4 w-4" />
								Add Podcast
							</Button>
						{/if}
					</div>
				{:else}
					<!-- Desktop Table -->
					<div class="hidden md:block">
						<Table.Root>
							<Table.Header>
								<Table.Row>
									<Table.Head>Feed</Table.Head>
									<Table.Head>Mode</Table.Head>
									<Table.Head>Max Items</Table.Head>
									<Table.Head>Status</Table.Head>
									<Table.Head class="w-[100px]">Actions</Table.Head>
								</Table.Row>
							</Table.Header>
							<Table.Body>
								{#each filteredFeeds as feed}
									<Table.Row>
										<Table.Cell>
											<div class="space-y-1">
												<p class="font-medium">{feed.title}</p>
												<a
													href={feed.url}
													target="_blank"
													rel="noopener noreferrer"
													class="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
												>
													{feed.url.length > 50 ? feed.url.substring(0, 50) + '...' : feed.url}
													<ExternalLink class="h-3 w-3" />
												</a>
											</div>
										</Table.Cell>
										<Table.Cell>
											<Badge variant={feed.mode === 'summarize' ? 'default' : 'secondary'}>
												{feed.mode}
											</Badge>
										</Table.Cell>
										<Table.Cell>{feed.max_items}</Table.Cell>
										<Table.Cell>
											<button
												type="button"
												class="inline-flex items-center gap-2"
												disabled={toggleFeedMutation.isPending && updatingFeedId === feed.id}
												onclick={() => handleToggleFeed(feed)}
											>
												<Badge variant={feed.is_active ? 'default' : 'outline'}>
													{feed.is_active ? 'Active' : 'Paused'}
												</Badge>
												{#if toggleFeedMutation.isPending && updatingFeedId === feed.id}
													<Loader2 class="h-3.5 w-3.5 animate-spin text-muted-foreground" />
												{/if}
											</button>
										</Table.Cell>
										<Table.Cell>
											<DropdownMenu.Root>
												<DropdownMenu.Trigger>
													{#snippet child({ props })}
														<Button {...props} variant="ghost" size="icon">
															<MoreHorizontal class="h-4 w-4" />
														</Button>
													{/snippet}
												</DropdownMenu.Trigger>
												<DropdownMenu.Content align="end">
													<DropdownMenu.Item onclick={() => handleEditFeed(feed)}>
														<Pencil class="mr-2 h-4 w-4" />
														Edit
													</DropdownMenu.Item>
													<DropdownMenu.Separator />
													<DropdownMenu.Item
														class="text-destructive"
														onclick={() => (feedToDelete = feed)}
													>
														<Trash2 class="mr-2 h-4 w-4" />
														Delete
													</DropdownMenu.Item>
												</DropdownMenu.Content>
											</DropdownMenu.Root>
										</Table.Cell>
									</Table.Row>
								{/each}
							</Table.Body>
						</Table.Root>
					</div>

					<!-- Mobile List -->
					<div class="md:hidden divide-y">
						{#each filteredFeeds as feed}
							<div class="p-4 space-y-2 overflow-hidden">
								<div class="flex items-start justify-between gap-2">
									<div class="min-w-0 flex-1 overflow-hidden">
										<p class="font-medium truncate">{feed.title}</p>
										<p class="text-xs text-muted-foreground truncate">{feed.url}</p>
									</div>
									<DropdownMenu.Root>
										<DropdownMenu.Trigger>
											{#snippet child({ props })}
												<Button {...props} variant="ghost" size="icon" class="flex-shrink-0 -mr-2">
													<MoreHorizontal class="h-4 w-4" />
												</Button>
											{/snippet}
										</DropdownMenu.Trigger>
										<DropdownMenu.Content align="end">
											<DropdownMenu.Item onclick={() => handleEditFeed(feed)}>
												<Pencil class="mr-2 h-4 w-4" />
												Edit
											</DropdownMenu.Item>
											<DropdownMenu.Separator />
											<DropdownMenu.Item class="text-destructive" onclick={() => (feedToDelete = feed)}>
												<Trash2 class="mr-2 h-4 w-4" />
												Delete
											</DropdownMenu.Item>
										</DropdownMenu.Content>
									</DropdownMenu.Root>
								</div>
								<div class="flex flex-wrap items-center gap-2">
									<Badge variant={feed.mode === 'summarize' ? 'default' : 'secondary'} class="text-xs">
										{feed.mode}
									</Badge>
									<button
										type="button"
										class="inline-flex items-center gap-2"
										disabled={toggleFeedMutation.isPending && updatingFeedId === feed.id}
										onclick={() => handleToggleFeed(feed)}
									>
										<Badge variant={feed.is_active ? 'default' : 'outline'} class="text-xs">
											{feed.is_active ? 'Active' : 'Paused'}
										</Badge>
									</button>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</Card.Content>
		</Card.Root>
	{:else}
		<!-- Transcripts List -->
		<Card.Root>
			<Card.Content class="p-0">
				{#if itemsQuery.isPending}
					<div class="p-4 space-y-3">
						{#each [1, 2, 3] as _}
							<div class="flex items-center gap-4">
								<Skeleton class="h-10 w-10 rounded" />
								<div class="flex-1 space-y-2">
									<Skeleton class="h-4 w-48" />
									<Skeleton class="h-3 w-32" />
								</div>
							</div>
						{/each}
					</div>
				{:else if !(itemsQuery.data ?? []).length}
					<div class="flex flex-col items-center justify-center py-12 text-center">
						<FileText class="h-12 w-12 text-muted-foreground/50" />
						<p class="mt-4 text-lg font-medium">No transcripts yet</p>
						<p class="text-sm text-muted-foreground">
							Completed podcast transcriptions will appear here
						</p>
					</div>
				{:else}
					<div class="divide-y">
						{#each processingItems as item}
							<div class="p-4 bg-muted/30">
								<div class="flex items-start justify-between gap-2">
									<div class="min-w-0 flex-1">
										<div class="flex items-center gap-2">
											<Loader2 class="h-4 w-4 animate-spin text-muted-foreground flex-shrink-0" />
											<p class="font-medium truncate">{item.title}</p>
										</div>
										{#if item.author}
											<p class="text-sm text-muted-foreground ml-6">{item.author}</p>
										{/if}
									</div>
									<Badge variant="secondary" class="text-xs flex-shrink-0">Processing</Badge>
								</div>
							</div>
						{/each}
						{#each pendingItems as item}
							<div class="p-4 bg-muted/15">
								<div class="flex items-start justify-between gap-2">
									<div class="min-w-0 flex-1">
										<div class="flex items-center gap-2">
											<Clock class="h-4 w-4 text-muted-foreground flex-shrink-0" />
											<p class="font-medium truncate">{item.title}</p>
										</div>
										{#if item.author}
											<p class="text-sm text-muted-foreground ml-6">{item.author}</p>
										{/if}
									</div>
									<Badge variant="outline" class="text-xs flex-shrink-0">Queued</Badge>
								</div>
							</div>
						{/each}
						{#if failedItems.length > 0}
							<div class="p-4 bg-destructive/5 border-y border-destructive/20">
								<div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
									<p class="text-xs text-muted-foreground">
										Failed transcripts are not retried automatically. Queue them for the next media processing run.
									</p>
									<Button
										size="sm"
										variant="outline"
										onclick={handleRetryAllFailed}
										disabled={retryAllFailedMutation.isPending || retryItemMutation.isPending}
									>
										{#if retryAllFailedMutation.isPending}
											<Loader2 class="mr-2 h-4 w-4 animate-spin" />
											Queueing...
										{:else}
											<RotateCcw class="mr-2 h-4 w-4" />
											Retry All Failed
										{/if}
									</Button>
								</div>
							</div>
						{/if}
						{#each failedItems as item}
							<div class="p-4">
								<div class="flex items-start justify-between gap-2">
									<div class="min-w-0 flex-1">
										<div class="flex items-center gap-2">
											<AlertCircle class="h-4 w-4 text-destructive flex-shrink-0" />
											<p class="font-medium truncate">{item.title}</p>
										</div>
										{#if item.error_message}
											<p class="text-xs text-destructive ml-6 mt-1">{item.error_message}</p>
											{#if item.error_message.toLowerCase().includes('timed out')}
												<a href="/settings" class="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground ml-6 mt-1">
													<Settings class="h-3 w-3" />
													Adjust timeout in Settings
												</a>
											{/if}
										{/if}
									</div>
									<div class="flex flex-col items-end gap-2 flex-shrink-0">
										<Badge variant="destructive" class="text-xs">Failed</Badge>
										<Button
											size="sm"
											variant="outline"
											onclick={() => handleRetryItem(item.id)}
											disabled={retryAllFailedMutation.isPending || retryItemMutation.isPending}
										>
											{#if retryItemMutation.isPending && retryingItemId === item.id}
												<Loader2 class="mr-2 h-3.5 w-3.5 animate-spin" />
												Queueing...
											{:else}
												Retry
											{/if}
										</Button>
									</div>
								</div>
							</div>
						{/each}
						{#each completedItems as item}
							<a
								href="/podcasts/items/{item.id}"
								class="block p-4 hover:bg-accent/50 transition-colors"
							>
								<div class="flex items-start justify-between gap-2">
									<div class="min-w-0 flex-1">
										<p class="font-medium">{item.title}</p>
										{#if item.author}
											<p class="text-sm text-muted-foreground">{item.author}</p>
										{/if}
									</div>
									<div class="flex flex-col items-end gap-1 flex-shrink-0">
										<Badge variant={item.is_summary ? 'default' : 'secondary'} class="text-xs">
											{item.is_summary ? 'Summary' : 'Transcript'}
										</Badge>
									</div>
								</div>
								<div class="mt-2 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
									<span>{item.word_count.toLocaleString()} words</span>
									{#if item.processing_ms > 0}
										<span class="inline-flex items-center gap-1">
											<Timer class="h-3 w-3" />
											{formatDuration(item.processing_ms)}
										</span>
									{/if}
									{#if item.completed_at}
										<span>{formatDate(item.completed_at)}</span>
									{/if}
									{#if item.consumed_at}
										<Badge variant="outline" class="text-xs">In digest</Badge>
									{/if}
								</div>
							</a>
						{/each}
					</div>
				{/if}
			</Card.Content>
		</Card.Root>
	{/if}
</div>

<!-- Add Feed Dialog -->
<Dialog.Root bind:open={addDialogOpen}>
	<Dialog.Content class="sm:max-w-md">
		<Dialog.Header>
			<Dialog.Title>Add Podcast Feed</Dialog.Title>
			<Dialog.Description>Add a podcast RSS feed for transcription</Dialog.Description>
		</Dialog.Header>
		<form onsubmit={handleAddFeed} class="space-y-4">
			<div class="space-y-2">
				<Label for="url">Feed URL</Label>
				<Input
					id="url"
					type="url"
					placeholder="https://example.com/podcast/feed.xml"
					bind:value={formUrl}
					required
				/>
			</div>
			<div class="space-y-2">
				<Label for="title">Title (optional)</Label>
				<Input id="title" placeholder="Podcast title" bind:value={formTitle} />
			</div>
			<div class="grid grid-cols-2 gap-4">
				<div class="space-y-2">
					<Label>Mode</Label>
					<Select.Root
						type="single"
						name="mode"
						value={formMode}
						onValueChange={(v) => (formMode = v as 'raw' | 'summarize')}
					>
						<Select.Trigger>
							<span class="capitalize">{formMode}</span>
						</Select.Trigger>
						<Select.Content>
							<Select.Item value="raw">Raw (Full Transcript)</Select.Item>
							<Select.Item value="summarize">Summarize</Select.Item>
						</Select.Content>
					</Select.Root>
				</div>
				<div class="space-y-2">
					<Label for="maxItems">Max Items</Label>
					<Input id="maxItems" type="number" min={1} max={20} bind:value={formMaxItems} />
				</div>
			</div>
			<Dialog.Footer>
				<Button type="button" variant="outline" onclick={() => (addDialogOpen = false)}>
					Cancel
				</Button>
				<Button type="submit" disabled={createFeedMutation.isPending}>
					{#if createFeedMutation.isPending}
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
						Adding...
					{:else}
						Add Podcast
					{/if}
				</Button>
			</Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>

<!-- Delete Confirmation -->
<AlertDialog.Root open={!!feedToDelete} onOpenChange={(open) => !open && (feedToDelete = null)}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Delete Podcast Feed</AlertDialog.Title>
			<AlertDialog.Description>
				Are you sure you want to delete "{feedToDelete?.title}"? This action cannot be undone.
			</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Cancel</AlertDialog.Cancel>
			<AlertDialog.Action
				onclick={confirmDelete}
				class="bg-destructive text-destructive-foreground hover:bg-destructive/90"
			>
				{#if deleteFeedMutation.isPending}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
				{/if}
				Delete
			</AlertDialog.Action>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>

<!-- Edit Feed Dialog -->
<Dialog.Root bind:open={editDialogOpen} onOpenChange={(open) => !open && (feedToEdit = null)}>
	<Dialog.Content class="sm:max-w-md">
		<Dialog.Header>
			<Dialog.Title>Edit Podcast Feed</Dialog.Title>
			<Dialog.Description>Update podcast feed settings</Dialog.Description>
		</Dialog.Header>
		<form onsubmit={handleUpdateFeed} class="space-y-4">
			<div class="space-y-2">
				<Label for="edit-url">Feed URL</Label>
				<Input id="edit-url" type="url" value={feedToEdit?.url ?? ''} disabled class="bg-muted" />
			</div>
			<div class="space-y-2">
				<Label for="edit-title">Title</Label>
				<Input id="edit-title" placeholder="Podcast title" bind:value={editTitle} required />
			</div>
			<div class="grid grid-cols-2 gap-4">
				<div class="space-y-2">
					<Label>Mode</Label>
					<Select.Root
						type="single"
						name="edit-mode"
						value={editMode}
						onValueChange={(v) => (editMode = v as 'raw' | 'summarize')}
					>
						<Select.Trigger>
							<span class="capitalize">{editMode}</span>
						</Select.Trigger>
						<Select.Content>
							<Select.Item value="raw">Raw (Full Transcript)</Select.Item>
							<Select.Item value="summarize">Summarize</Select.Item>
						</Select.Content>
					</Select.Root>
				</div>
				<div class="space-y-2">
					<Label for="edit-maxItems">Max Items</Label>
					<Input id="edit-maxItems" type="number" min={1} max={20} bind:value={editMaxItems} />
				</div>
			</div>
			<div class="flex items-center justify-between rounded-lg border p-3">
				<div class="space-y-0.5">
					<Label for="edit-active">Active</Label>
					<p class="text-xs text-muted-foreground">Include this feed in processing</p>
				</div>
				<Switch id="edit-active" bind:checked={editIsActive} />
			</div>
			<Dialog.Footer>
				<Button type="button" variant="outline" onclick={() => (editDialogOpen = false)}>
					Cancel
				</Button>
				<Button type="submit" disabled={updateFeedMutation.isPending}>
					{#if updateFeedMutation.isPending}
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
						Saving...
					{:else}
						Save Changes
					{/if}
				</Button>
			</Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>
