<script lang="ts">
	import { createQuery, createMutation, useQueryClient } from '@tanstack/svelte-query';
	import { api } from '$lib/api/client';
	import type { PodcastEpisodeStatusResponse } from '$lib/api/types';
	import * as AlertDialog from '$lib/components/ui/alert-dialog';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import { Label } from '$lib/components/ui/label';
	import { Input } from '$lib/components/ui/input';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import * as Select from '$lib/components/ui/select';
	import * as Table from '$lib/components/ui/table';
	import { formatUTCDate, parseUTC } from '$lib/utils/date';
	import {
		getEpisodeStatusBadgeVariant,
		getEpisodeStatusLabel,
		isEpisodeActive,
		formatDuration,
		formatCost
	} from '$lib/utils/episode';
	import {
		Calendar,
		Download,
		Headphones,
		Loader2,
		Mic,
		Play,
		RefreshCw,
		RotateCcw,
		Trash2,
		Volume2
	} from 'lucide-svelte';
	import { toast } from 'svelte-sonner';

	const queryClient = useQueryClient();

	// Queries
	const episodesQuery = createQuery(() => ({
		queryKey: ['podcast-episodes'],
		queryFn: () => api.getPodcastEpisodes(),
		refetchInterval: (query) => {
			const hasActive = query.state.data?.some((ep) => isEpisodeActive(ep.status));
			return hasActive ? 5000 : false;
		}
	}));

	// Mutations
	const generateMutation = createMutation(() => ({
		mutationFn: () => api.generateScheduledEpisode(),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['podcast-episodes'] });
			toast.success('Episode generation started');
		},
		onError: (err: Error) => {
			toast.error('Failed to generate episode', { description: err.message });
		}
	}));

	const deleteMutation = createMutation(() => ({
		mutationFn: (id: string) => api.deletePodcastEpisode(id),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['podcast-episodes'] });
			toast.success('Episode deleted');
			episodeToDelete = null;
		},
		onError: (err: Error) => {
			toast.error('Failed to delete episode', { description: err.message });
		}
	}));

	const retryMutation = createMutation(() => ({
		mutationFn: (id: string) => api.retryPodcastEpisode(id),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['podcast-episodes'] });
			toast.success('Episode retry queued');
		},
		onError: (err: Error) => {
			toast.error('Failed to retry episode', { description: err.message });
		},
		onSettled: () => {
			retryingId = null;
		}
	}));

	// State
	let statusFilter = $state<string>('all');
	let triggerFilter = $state<string>('all');
	let fromDate = $state('');
	let toDate = $state('');
	let sortBy = $state<'created_at' | 'duration_seconds' | 'article_count'>('created_at');
	let sortOrder = $state<'desc' | 'asc'>('desc');
	let episodeToDelete = $state<PodcastEpisodeStatusResponse | null>(null);
	let retryingId = $state<string | null>(null);
	let downloadPendingById = $state<Record<string, boolean>>({});

	// Derived
	const visibleEpisodes = $derived.by(() => {
		const episodes = episodesQuery.data ?? [];
		const fromBoundary = fromDate ? toDateStart(fromDate) : null;
		const toBoundary = toDate ? toDateEnd(toDate) : null;

		const filtered = episodes.filter((ep) => {
			if (statusFilter !== 'all' && ep.status !== statusFilter) return false;
			if (triggerFilter !== 'all' && ep.trigger !== triggerFilter) return false;
			const createdAt = parseUTC(ep.created_at).getTime();
			if (fromBoundary && createdAt < fromBoundary.getTime()) return false;
			if (toBoundary && createdAt > toBoundary.getTime()) return false;
			return true;
		});

		const multiplier = sortOrder === 'asc' ? 1 : -1;
		return filtered.sort((a, b) => {
			if (sortBy === 'created_at') {
				return (parseUTC(a.created_at).getTime() - parseUTC(b.created_at).getTime()) * multiplier;
			}
			if (sortBy === 'duration_seconds') {
				return ((a.duration_seconds ?? 0) - (b.duration_seconds ?? 0)) * multiplier;
			}
			return (a.article_count - b.article_count) * multiplier;
		});
	});

	const hasActiveEpisode = $derived(
		(episodesQuery.data ?? []).some((ep) => isEpisodeActive(ep.status))
	);

	function formatDate(dateStr: string): string {
		return formatUTCDate(dateStr, {
			weekday: 'short',
			month: 'short',
			day: 'numeric',
			hour: 'numeric',
			minute: '2-digit'
		});
	}

	function formatShortDate(dateStr: string): string {
		return formatUTCDate(dateStr, { month: 'short', day: 'numeric' });
	}

	function toDateStart(value: string): Date {
		const [year, month, day] = value.split('-').map(Number);
		return new Date(year, month - 1, day, 0, 0, 0, 0);
	}

	function toDateEnd(value: string): Date {
		const [year, month, day] = value.split('-').map(Number);
		return new Date(year, month - 1, day, 23, 59, 59, 999);
	}

	function clearFilters() {
		statusFilter = 'all';
		triggerFilter = 'all';
		fromDate = '';
		toDate = '';
		sortBy = 'created_at';
		sortOrder = 'desc';
	}

	function handleRetry(id: string) {
		retryingId = id;
		retryMutation.mutate(id);
	}

	async function handleDownload(episode: PodcastEpisodeStatusResponse) {
		if (!episode.download_url) return;
		downloadPendingById = { ...downloadPendingById, [episode.id]: true };
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
			downloadPendingById = { ...downloadPendingById, [episode.id]: false };
		}
	}
</script>

<svelte:head>
	<title>Episodes - Ghostwriter</title>
</svelte:head>

<div class="space-y-6">
	<div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
		<div>
			<h1 class="text-2xl font-bold tracking-tight">Episodes</h1>
			<p class="text-muted-foreground">Generated podcast episodes from your digests</p>
		</div>
		<div class="flex items-center gap-2">
			<Button
				variant="outline"
				size="icon"
				onclick={() => episodesQuery.refetch()}
				disabled={episodesQuery.isFetching}
			>
				<RefreshCw class="h-4 w-4 {episodesQuery.isFetching ? 'animate-spin' : ''}" />
			</Button>
			<Button
				onclick={() => generateMutation.mutate()}
				disabled={generateMutation.isPending || hasActiveEpisode}
			>
				{#if generateMutation.isPending || hasActiveEpisode}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					{hasActiveEpisode ? 'Generating...' : 'Starting...'}
				{:else}
					<Play class="mr-2 h-4 w-4" />
					Generate Episode
				{/if}
			</Button>
		</div>
	</div>

	<!-- Filters -->
	<Card.Root>
		<Card.Header class="space-y-4">
			<div class="grid gap-3 md:grid-cols-2 lg:grid-cols-5">
				<div class="space-y-2">
					<Label for="ep-status-filter">Status</Label>
					<Select.Root
						type="single"
						name="ep-status-filter"
						value={statusFilter}
						onValueChange={(v) => (statusFilter = v)}
					>
						<Select.Trigger id="ep-status-filter">
							<span class="capitalize">{statusFilter === 'all' ? 'All statuses' : getEpisodeStatusLabel(statusFilter)}</span>
						</Select.Trigger>
						<Select.Content>
							<Select.Item value="all">All statuses</Select.Item>
							<Select.Item value="pending">Queued</Select.Item>
							<Select.Item value="generating_script">Generating script</Select.Item>
							<Select.Item value="generating_audio">Generating audio</Select.Item>
							<Select.Item value="ready">Ready</Select.Item>
							<Select.Item value="failed">Failed</Select.Item>
						</Select.Content>
					</Select.Root>
				</div>
				<div class="space-y-2">
					<Label for="ep-trigger-filter">Trigger</Label>
					<Select.Root
						type="single"
						name="ep-trigger-filter"
						value={triggerFilter}
						onValueChange={(v) => (triggerFilter = v)}
					>
						<Select.Trigger id="ep-trigger-filter">
							<span class="capitalize">{triggerFilter === 'all' ? 'All triggers' : triggerFilter}</span>
						</Select.Trigger>
						<Select.Content>
							<Select.Item value="all">All triggers</Select.Item>
							<Select.Item value="manual">Manual</Select.Item>
							<Select.Item value="scheduled">Scheduled</Select.Item>
						</Select.Content>
					</Select.Root>
				</div>
				<div class="space-y-2">
					<Label for="ep-from-date">From</Label>
					<Input id="ep-from-date" type="date" bind:value={fromDate} />
				</div>
				<div class="space-y-2">
					<Label for="ep-to-date">To</Label>
					<Input id="ep-to-date" type="date" bind:value={toDate} />
				</div>
				<div class="space-y-2">
					<Label for="ep-sort">Sort</Label>
					<div class="flex gap-2">
						<Select.Root
							type="single"
							name="ep-sort"
							value={sortBy}
							onValueChange={(v) => (sortBy = v as typeof sortBy)}
						>
							<Select.Trigger id="ep-sort" class="flex-1">
								<span>
									{sortBy === 'created_at' ? 'Date' : sortBy === 'duration_seconds' ? 'Duration' : 'Articles'}
								</span>
							</Select.Trigger>
							<Select.Content>
								<Select.Item value="created_at">Date</Select.Item>
								<Select.Item value="duration_seconds">Duration</Select.Item>
								<Select.Item value="article_count">Articles</Select.Item>
							</Select.Content>
						</Select.Root>
						<Button
							variant="outline"
							size="sm"
							onclick={() => (sortOrder = sortOrder === 'asc' ? 'desc' : 'asc')}
						>
							{sortOrder === 'asc' ? 'Asc' : 'Desc'}
						</Button>
					</div>
				</div>
			</div>
			<div class="flex items-center justify-between">
				<span class="text-sm text-muted-foreground">
					Showing {visibleEpisodes.length} episode{visibleEpisodes.length !== 1 ? 's' : ''}
				</span>
				<Button size="sm" variant="ghost" onclick={clearFilters}>Reset filters</Button>
			</div>
		</Card.Header>
	</Card.Root>

	<!-- Episode List -->
	<Card.Root>
		<Card.Content class="p-0">
			{#if episodesQuery.isPending}
				<div class="p-4 space-y-3">
					{#each [1, 2, 3, 4, 5] as _}
						<div class="flex items-center gap-4">
							<Skeleton class="h-10 w-10 rounded" />
							<div class="flex-1 space-y-2">
								<Skeleton class="h-4 w-32" />
								<Skeleton class="h-3 w-24" />
							</div>
							<Skeleton class="h-8 w-28" />
						</div>
					{/each}
				</div>
			{:else if !visibleEpisodes.length}
				<div class="flex flex-col items-center justify-center py-12 text-center">
					<Mic class="h-12 w-12 text-muted-foreground/50" />
					<p class="mt-4 text-lg font-medium">
						{(episodesQuery.data ?? []).length > 0 ? 'No episodes match filters' : 'No episodes yet'}
					</p>
					<p class="text-sm text-muted-foreground">
						{(episodesQuery.data ?? []).length > 0
							? 'Try different filter settings'
							: 'Generate an episode from your digests to get started'}
					</p>
					{#if !(episodesQuery.data ?? []).length}
						<Button
							class="mt-4"
							onclick={() => generateMutation.mutate()}
							disabled={generateMutation.isPending}
						>
							<Play class="mr-2 h-4 w-4" />
							Generate Episode
						</Button>
					{/if}
				</div>
			{:else}
				<!-- Desktop Table -->
				<div class="hidden md:block">
					<Table.Root>
						<Table.Header>
							<Table.Row>
								<Table.Head>Date</Table.Head>
								<Table.Head>Status</Table.Head>
								<Table.Head>Trigger</Table.Head>
								<Table.Head>Articles</Table.Head>
								<Table.Head>Duration</Table.Head>
								<Table.Head>Cost</Table.Head>
								<Table.Head class="w-[240px]">Actions</Table.Head>
							</Table.Row>
						</Table.Header>
						<Table.Body>
							{#each visibleEpisodes as episode}
								<Table.Row>
									<Table.Cell>
										<div class="flex items-center gap-2">
											<Calendar class="h-4 w-4 text-muted-foreground" />
											{formatDate(episode.created_at)}
										</div>
										{#if episode.title}
											<p class="mt-1 max-w-56 truncate text-sm text-muted-foreground" title={episode.title}>
												{episode.title}
											</p>
										{/if}
									</Table.Cell>
									<Table.Cell>
										<Badge variant={getEpisodeStatusBadgeVariant(episode.status)}>
											{getEpisodeStatusLabel(episode.status)}
										</Badge>
										{#if episode.error_message}
											<p class="mt-1 max-w-48 truncate text-xs text-destructive" title={episode.error_message}>
												{episode.error_message}
											</p>
										{/if}
									</Table.Cell>
									<Table.Cell class="capitalize">{episode.trigger}</Table.Cell>
									<Table.Cell>{episode.article_count}</Table.Cell>
									<Table.Cell>
										{#if episode.duration_seconds}
											{formatDuration(episode.duration_seconds)}
										{:else}
											<span class="text-muted-foreground">—</span>
										{/if}
									</Table.Cell>
									<Table.Cell>
										{#if episode.generation_cost_cents}
											{formatCost(episode.generation_cost_cents)}
										{:else}
											<span class="text-muted-foreground">—</span>
										{/if}
									</Table.Cell>
									<Table.Cell>
										<div class="flex flex-wrap items-center gap-2">
											{#if episode.status === 'ready'}
												<a href="/episodes/{episode.id}">
													<Button size="sm" variant="outline">
														<Headphones class="mr-2 h-4 w-4" />
														Listen
													</Button>
												</a>
												<Button
													size="sm"
													variant="outline"
													onclick={() => handleDownload(episode)}
													disabled={!!downloadPendingById[episode.id]}
												>
													{#if downloadPendingById[episode.id]}
														<Loader2 class="mr-2 h-4 w-4 animate-spin" />
														Preparing...
													{:else}
														<Download class="mr-2 h-4 w-4" />
														MP3
													{/if}
												</Button>
											{/if}
											{#if episode.status === 'failed'}
												<Button
													size="sm"
													variant="outline"
													onclick={() => handleRetry(episode.id)}
													disabled={retryMutation.isPending}
												>
													{#if retryingId === episode.id && retryMutation.isPending}
														<Loader2 class="mr-2 h-4 w-4 animate-spin" />
														Retrying...
													{:else}
														<RotateCcw class="mr-2 h-4 w-4" />
														Retry
													{/if}
												</Button>
											{/if}
											{#if isEpisodeActive(episode.status)}
												<Badge variant="secondary" class="gap-1">
													<Loader2 class="h-3 w-3 animate-spin" />
													{getEpisodeStatusLabel(episode.status)}
												</Badge>
											{/if}
											<Button
												size="sm"
												variant="outline"
												class="text-destructive hover:text-destructive"
												onclick={() => (episodeToDelete = episode)}
											>
												<Trash2 class="mr-2 h-4 w-4" />
												Delete
											</Button>
										</div>
									</Table.Cell>
								</Table.Row>
							{/each}
						</Table.Body>
					</Table.Root>
				</div>

				<!-- Mobile List -->
				<div class="divide-y md:hidden">
					{#each visibleEpisodes as episode}
						<div class="space-y-3 p-4">
							<div class="flex items-start justify-between gap-2">
								<div class="min-w-0 flex-1">
									{#if episode.title}
										<p class="truncate font-medium" title={episode.title}>{episode.title}</p>
									{:else}
										<p class="font-medium capitalize">{episode.trigger} episode</p>
									{/if}
									<p class="text-sm text-muted-foreground">{formatDate(episode.created_at)}</p>
								</div>
								<Badge variant={getEpisodeStatusBadgeVariant(episode.status)}>
									{getEpisodeStatusLabel(episode.status)}
								</Badge>
							</div>
							<div class="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
								<span>{episode.article_count} articles</span>
								{#if episode.duration_seconds}
									<span>{formatDuration(episode.duration_seconds)}</span>
								{/if}
								{#if episode.generation_cost_cents}
									<span>{formatCost(episode.generation_cost_cents)}</span>
								{/if}
							</div>
							{#if episode.error_message}
								<p class="text-xs text-destructive">{episode.error_message}</p>
							{/if}
							<div class="flex flex-wrap items-center gap-2">
								{#if episode.status === 'ready'}
									<a href="/episodes/{episode.id}">
										<Button size="sm" variant="outline">
											<Headphones class="mr-2 h-4 w-4" />
											Listen
										</Button>
									</a>
									<Button
										size="sm"
										variant="outline"
										onclick={() => handleDownload(episode)}
										disabled={!!downloadPendingById[episode.id]}
									>
										{#if downloadPendingById[episode.id]}
											<Loader2 class="mr-2 h-4 w-4 animate-spin" />
										{:else}
											<Download class="mr-2 h-4 w-4" />
										{/if}
										MP3
									</Button>
								{/if}
								{#if episode.status === 'failed'}
									<Button
										size="sm"
										variant="outline"
										onclick={() => handleRetry(episode.id)}
										disabled={retryMutation.isPending}
									>
										<RotateCcw class="mr-2 h-4 w-4" />
										Retry
									</Button>
								{/if}
								{#if isEpisodeActive(episode.status)}
									<Badge variant="secondary" class="gap-1">
										<Loader2 class="h-3 w-3 animate-spin" />
										{getEpisodeStatusLabel(episode.status)}
									</Badge>
								{/if}
								<Button
									size="sm"
									variant="outline"
									class="text-destructive hover:text-destructive"
									onclick={() => (episodeToDelete = episode)}
								>
									<Trash2 class="mr-2 h-4 w-4" />
									Delete
								</Button>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</Card.Content>
	</Card.Root>
</div>

<!-- Delete Confirmation -->
<AlertDialog.Root open={!!episodeToDelete} onOpenChange={(open) => !open && (episodeToDelete = null)}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Delete Episode</AlertDialog.Title>
			<AlertDialog.Description>
				Are you sure you want to delete the {episodeToDelete?.trigger} episode from{' '}
				{episodeToDelete ? formatShortDate(episodeToDelete.created_at) : ''}? The audio file will also be removed.
			</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Cancel</AlertDialog.Cancel>
			<AlertDialog.Action
				onclick={() => episodeToDelete && deleteMutation.mutate(episodeToDelete.id)}
				class="bg-destructive text-destructive-foreground hover:bg-destructive/90"
			>
				{#if deleteMutation.isPending}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
				{/if}
				Delete
			</AlertDialog.Action>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>
