<script lang="ts">
	import { goto } from '$app/navigation';
	import { onDestroy } from 'svelte';
	import { createMutation, createQuery, useQueryClient } from '@tanstack/svelte-query';
	import { api, ApiError, type Digest, type DigestPeriod, type DigestStatus } from '$lib/api';
	import * as AlertDialog from '$lib/components/ui/alert-dialog';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Progress } from '$lib/components/ui/progress';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import * as Select from '$lib/components/ui/select';
	import * as Table from '$lib/components/ui/table';
	import { formatUTCDate, parseUTC } from '$lib/utils/date';
	import { downloadDigestFileById, getDigestStatusBadgeVariant, type DigestFileFormat } from '$lib/utils/digest';
	import {
		BookCopy,
		Calendar,
		Download,
		Eye,
		Loader2,
		LayoutGrid,
		List,
		Mic,
		Play,
		RefreshCw,
		Trash2
	} from 'lucide-svelte';
	import { toast } from 'svelte-sonner';

	const queryClient = useQueryClient();
	const PAGE_SIZE = 20;
	const ACTIVE_PODCAST_STATUSES = new Set(['pending', 'generating_script', 'generating_audio']);

	let limit = $state(PAGE_SIZE);
	let statusFilter = $state<'all' | DigestStatus>('all');
	let periodFilter = $state<'all' | DigestPeriod>('all');
	let fromDate = $state('');
	let toDate = $state('');
	let sortBy = $state<'created_at' | 'total_articles' | 'duration'>('created_at');
	let sortOrder = $state<'desc' | 'asc'>('desc');
	let viewMode = $state<'list' | 'covers'>('list');
	let digestToDelete = $state<Digest | null>(null);
	let lastFilterSignature = $state('all:all');
	let digestCoverUrls = $state<Record<string, string>>({});
	let digestCoverErrors = $state<Record<string, boolean>>({});
	let downloadPendingByKey = $state<Record<string, boolean>>({});
	let podcastTriggerPendingByDigest = $state<Record<string, boolean>>({});
	let podcastStatusByDigest = $state<Record<string, { status: string; error_message?: string | null }>>({});
	let coverLoadToken = 0;
	let podcastStatusLoadToken = 0;
	let podcastStatusPollTimer: ReturnType<typeof setInterval> | null = null;

	const queryParams = $derived.by(() => ({
		limit,
		status: statusFilter === 'all' ? undefined : statusFilter,
		period: periodFilter === 'all' ? undefined : periodFilter
	}));

	const digestsQuery = createQuery(() => ({
		queryKey: ['digests', queryParams.status, queryParams.period, queryParams.limit],
		queryFn: () => api.getDigests(queryParams),
		staleTime: 30 * 1000,
		refetchOnWindowFocus: false,
		refetchInterval: (query) => {
			const hasProcessing = query.state.data?.some((digest) => digest.status === 'processing');
			return hasProcessing ? 5000 : 30000;
		}
	}));

	const triggerMutation = createMutation(() => ({
		mutationFn: () => api.triggerDigest(),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['digests'] });
			toast.success('Digest generation started');
		},
		onError: (err: Error) => {
			toast.error('Failed to trigger digest', {
				description: err.message ?? 'Unknown error'
			});
		}
	}));

	const deleteMutation = createMutation(() => ({
		mutationFn: (filename: string) => api.deleteDigest(filename),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['digests'] });
			toast.success('Digest deleted');
			digestToDelete = null;
		},
		onError: (err: Error) => {
			toast.error('Failed to delete digest', {
				description: err.message ?? 'Unknown error'
			});
		}
	}));

	const triggerPodcastMutation = createMutation(() => ({
		mutationFn: (digestId: string) => api.triggerDigestPodcast(digestId)
	}));

	$effect(() => {
		const signature = `${statusFilter}:${periodFilter}`;
		if (signature === lastFilterSignature) return;
		lastFilterSignature = signature;
		limit = PAGE_SIZE;
	});

	const loadedDigests = $derived(digestsQuery.data ?? []);
	const processingDigest = $derived(loadedDigests.find((digest) => digest.status === 'processing'));
	const hasMore = $derived(loadedDigests.length >= limit);

	const visibleDigests = $derived.by(() => {
		const fromBoundary = fromDate ? toDateStart(fromDate) : null;
		const toBoundary = toDate ? toDateEnd(toDate) : null;

		const filtered = loadedDigests.filter((digest) => {
			const createdAt = parseUTC(digest.created_at).getTime();
			if (fromBoundary && createdAt < fromBoundary.getTime()) return false;
			if (toBoundary && createdAt > toBoundary.getTime()) return false;
			return true;
		});

		const multiplier = sortOrder === 'asc' ? 1 : -1;
		return filtered.sort((left, right) => {
			if (sortBy === 'created_at') {
				return (parseUTC(left.created_at).getTime() - parseUTC(right.created_at).getTime()) * multiplier;
			}

			if (sortBy === 'total_articles') {
				return (left.total_articles - right.total_articles) * multiplier;
			}

			const leftDuration = getDurationSeconds(left) ?? -1;
			const rightDuration = getDurationSeconds(right) ?? -1;
			return (leftDuration - rightDuration) * multiplier;
		});
	});

	$effect(() => {
		const nextIds = new Set(visibleDigests.map((digest) => digest.id));
		for (const [id, url] of Object.entries(digestCoverUrls)) {
			if (!nextIds.has(id)) {
				URL.revokeObjectURL(url);
				const next = { ...digestCoverUrls };
				delete next[id];
				digestCoverUrls = next;
			}
		}
	});

	$effect(() => {
		const nextIds = new Set(visibleDigests.map((digest) => digest.id));
		for (const digestId of Object.keys(podcastStatusByDigest)) {
			if (!nextIds.has(digestId)) {
				const next = { ...podcastStatusByDigest };
				delete next[digestId];
				podcastStatusByDigest = next;
			}
		}
		for (const digestId of Object.keys(podcastTriggerPendingByDigest)) {
			if (!nextIds.has(digestId)) {
				const next = { ...podcastTriggerPendingByDigest };
				delete next[digestId];
				podcastTriggerPendingByDigest = next;
			}
		}
	});

	$effect(() => {
		const localToken = coverLoadToken + 1;
		coverLoadToken = localToken;

		async function loadCovers() {
			for (const digest of visibleDigests) {
				if (digestCoverUrls[digest.id] || digestCoverErrors[digest.id]) continue;
				if (digest.status !== 'completed' || !digest.filename) continue;
				try {
					const { blob } = await api.downloadDigestCover(digest.id);
					if (coverLoadToken !== localToken) return;
					const objectUrl = URL.createObjectURL(blob);
					digestCoverUrls = {
						...digestCoverUrls,
						[digest.id]: objectUrl
					};
				} catch {
					if (coverLoadToken !== localToken) return;
					digestCoverErrors = {
						...digestCoverErrors,
						[digest.id]: true
					};
				}
			}
		}

		void loadCovers();
	});

	async function refreshPodcastStatuses(digestIds: string[], token: number) {
		const results = await Promise.all(
			digestIds.map(async (digestId) => {
				try {
					const data = await api.getDigestPodcastStatus(digestId);
					return [digestId, {
						status: data.episode.status,
						error_message: data.episode.error_message
					}] as const;
				} catch (err) {
					if (err instanceof ApiError && err.isNotFound) {
						return [digestId, null] as const;
					}
					return [digestId, podcastStatusByDigest[digestId] ?? null] as const;
				}
			})
		);
		if (podcastStatusLoadToken !== token) return;
		const next = { ...podcastStatusByDigest };
		for (const [digestId, status] of results) {
			if (!status) {
				delete next[digestId];
			} else {
				next[digestId] = status;
			}
		}
		podcastStatusByDigest = next;
	}

	$effect(() => {
		const digestIds = visibleDigests
			.filter((digest) => digest.status === 'completed')
			.map((digest) => digest.id);
		const localToken = podcastStatusLoadToken + 1;
		podcastStatusLoadToken = localToken;
		if (!digestIds.length) {
			if (podcastStatusPollTimer) {
				clearInterval(podcastStatusPollTimer);
				podcastStatusPollTimer = null;
			}
			return;
		}

		void refreshPodcastStatuses(digestIds, localToken);

		const hasActive = digestIds.some((digestId) =>
			ACTIVE_PODCAST_STATUSES.has(podcastStatusByDigest[digestId]?.status ?? '')
		);
		if (podcastStatusPollTimer) {
			clearInterval(podcastStatusPollTimer);
			podcastStatusPollTimer = null;
		}
		if (hasActive) {
			podcastStatusPollTimer = setInterval(() => {
				void refreshPodcastStatuses(digestIds, localToken);
			}, 3000);
		}
	});

	onDestroy(() => {
		for (const url of Object.values(digestCoverUrls)) {
			URL.revokeObjectURL(url);
		}
		if (podcastStatusPollTimer) {
			clearInterval(podcastStatusPollTimer);
		}
	});

	function openReader(digest: Digest) {
		goto(`/digests/${digest.id}/read`);
	}

	function canGeneratePodcast(digest: Digest): boolean {
		if (digest.status !== 'completed') return false;
		const currentStatus = podcastStatusByDigest[digest.id]?.status;
		return !ACTIVE_PODCAST_STATUSES.has(currentStatus ?? '');
	}

	function isPodcastTriggerPending(digestId: string): boolean {
		return !!podcastTriggerPendingByDigest[digestId];
	}

	function getPodcastStatusLabel(digestId: string): string | null {
		const status = podcastStatusByDigest[digestId]?.status;
		if (!status) return null;
		if (status === 'pending') return 'Podcast queued';
		if (status === 'generating_script') return 'Generating script';
		if (status === 'generating_audio') return 'Generating audio';
		if (status === 'ready') return 'Podcast ready';
		if (status === 'failed') return 'Podcast failed';
		return `Podcast ${status}`;
	}

	function isPodcastStatusActive(digestId: string): boolean {
		const status = podcastStatusByDigest[digestId]?.status;
		return ACTIVE_PODCAST_STATUSES.has(status ?? '');
	}

	function isPodcastStatusFailed(digestId: string): boolean {
		return podcastStatusByDigest[digestId]?.status === 'failed';
	}

	function getPodcastStatusError(digestId: string): string | null {
		return podcastStatusByDigest[digestId]?.error_message ?? null;
	}

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
		return formatUTCDate(dateStr, {
			month: 'short',
			day: 'numeric'
		});
	}

	function getDurationSeconds(digest: Digest): number | null {
		if (!digest.completed_at) return null;
		const start = parseUTC(digest.created_at).getTime();
		const end = parseUTC(digest.completed_at).getTime();
		return Math.max(0, Math.round((end - start) / 1000));
	}

	function getDurationLabel(digest: Digest): string | null {
		const seconds = getDurationSeconds(digest);
		if (seconds === null) return null;
		if (seconds < 60) return `${seconds}s`;
		const minutes = Math.floor(seconds / 60);
		const remainingSeconds = seconds % 60;
		return `${minutes}m ${remainingSeconds}s`;
	}

	function toDateStart(value: string): Date {
		const [year, month, day] = value.split('-').map(Number);
		return new Date(year, month - 1, day, 0, 0, 0, 0);
	}

	function toDateEnd(value: string): Date {
		const [year, month, day] = value.split('-').map(Number);
		return new Date(year, month - 1, day, 23, 59, 59, 999);
	}

	function formatDateInput(date: Date): string {
		const year = date.getFullYear();
		const month = `${date.getMonth() + 1}`.padStart(2, '0');
		const day = `${date.getDate()}`.padStart(2, '0');
		return `${year}-${month}-${day}`;
	}

	function setLastDays(days: number) {
		const now = new Date();
		const start = new Date(now);
		start.setDate(start.getDate() - days + 1);
		fromDate = formatDateInput(start);
		toDate = formatDateInput(now);
	}

	function setThisMonth() {
		const now = new Date();
		const start = new Date(now.getFullYear(), now.getMonth(), 1);
		fromDate = formatDateInput(start);
		toDate = formatDateInput(now);
	}

	function clearDateRange() {
		fromDate = '';
		toDate = '';
	}

	function clearFilters() {
		statusFilter = 'all';
		periodFilter = 'all';
		sortBy = 'created_at';
		sortOrder = 'desc';
		clearDateRange();
	}

	function loadMore() {
		limit += PAGE_SIZE;
	}

	function getCoverUrl(digest: Digest): string | null {
		return digestCoverUrls[digest.id] ?? null;
	}

	function fallbackFilename(digest: Digest, format: DigestFileFormat): string {
		if (!digest.filename) return `${digest.id}.${format}`;
		if (format === 'epub') return digest.filename;
		if (digest.filename.includes('.')) {
			return `${digest.filename.slice(0, digest.filename.lastIndexOf('.'))}.pdf`;
		}
		return `${digest.filename}.pdf`;
	}

	function supportsFormat(digest: Digest, format: DigestFileFormat): boolean {
		const available = digest.available_formats;
		if (!available || available.length === 0) {
			return format === 'epub';
		}
		return available.includes(format);
	}

	function downloadKey(digest: Digest, format: DigestFileFormat): string {
		return `${digest.id}:${format}`;
	}

	function isDownloadPending(digest: Digest, format: DigestFileFormat): boolean {
		return !!downloadPendingByKey[downloadKey(digest, format)];
	}

	async function downloadDigest(digest: Digest, format: DigestFileFormat) {
		const key = downloadKey(digest, format);
		downloadPendingByKey = { ...downloadPendingByKey, [key]: true };
		try {
			await downloadDigestFileById(digest.id, format, fallbackFilename(digest, format));
		} catch (err) {
			const message = err instanceof Error ? err.message : 'Unknown error';
			toast.error(`Failed to download ${format.toUpperCase()}`, { description: message });
		} finally {
			downloadPendingByKey = { ...downloadPendingByKey, [key]: false };
		}
	}

	async function triggerDigestPodcast(digest: Digest) {
		if (!canGeneratePodcast(digest)) return;
		podcastTriggerPendingByDigest = {
			...podcastTriggerPendingByDigest,
			[digest.id]: true
		};
		try {
			const response = await triggerPodcastMutation.mutateAsync(digest.id);
			podcastStatusByDigest = {
				...podcastStatusByDigest,
				[digest.id]: {
					status: response.status
				}
			};
			queryClient.invalidateQueries({ queryKey: ['digests'] });
			toast.success('Podcast generation queued');
		} catch (err) {
			const message = err instanceof Error ? err.message : 'Unknown error';
			toast.error('Failed to generate podcast', {
				description: message
			});
		} finally {
			podcastTriggerPendingByDigest = {
				...podcastTriggerPendingByDigest,
				[digest.id]: false
			};
		}
	}
</script>

<svelte:head>
	<title>Digests - Ghostwriter</title>
</svelte:head>

<div class="space-y-6">
	<div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
		<div>
			<h1 class="text-2xl font-bold tracking-tight">Digests</h1>
			<p class="text-muted-foreground">Find, read, and manage generated digests</p>
		</div>
		<div class="flex items-center gap-2">
			<Button
				variant="outline"
				size="icon"
				onclick={() => digestsQuery.refetch()}
				disabled={digestsQuery.isFetching}
			>
				<RefreshCw class="h-4 w-4 {digestsQuery.isFetching ? 'animate-spin' : ''}" />
			</Button>
			<Button onclick={() => triggerMutation.mutate()} disabled={triggerMutation.isPending || !!processingDigest}>
				{#if triggerMutation.isPending || processingDigest}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					{processingDigest ? 'Processing...' : 'Starting...'}
				{:else}
					<Play class="mr-2 h-4 w-4" />
					Generate Digest
				{/if}
			</Button>
		</div>
	</div>

	{#if processingDigest}
		<Card.Root>
			<Card.Header>
				<Card.Title class="flex items-center gap-2">
					<Loader2 class="h-4 w-4 animate-spin" />
					Generating Digest
				</Card.Title>
				<Card.Description>
					{processingDigest.stage ?? 'Processing'} • {processingDigest.period}
				</Card.Description>
			</Card.Header>
			<Card.Content class="space-y-4">
				<div class="space-y-2">
					<div class="flex justify-between text-sm">
						<span>Feeds fetched</span>
						<span>{processingDigest.feeds_fetched}/{processingDigest.total_feeds}</span>
					</div>
					<Progress
						value={processingDigest.total_feeds > 0
							? (processingDigest.feeds_fetched / processingDigest.total_feeds) * 100
							: 0}
					/>
				</div>
				<div class="space-y-2">
					<div class="flex justify-between text-sm">
						<span>Articles enriched</span>
						<span>{processingDigest.articles_enriched}/{processingDigest.total_articles}</span>
					</div>
					<Progress
						value={processingDigest.total_articles > 0
							? (processingDigest.articles_enriched / processingDigest.total_articles) * 100
							: 0}
					/>
				</div>
			</Card.Content>
		</Card.Root>
	{/if}

	<Card.Root>
		<Card.Header class="space-y-4">
			<div class="grid gap-3 md:grid-cols-2 lg:grid-cols-5">
				<div class="space-y-2">
					<Label for="digest-status-filter">Status</Label>
					<Select.Root
						type="single"
						name="digest-status-filter"
						value={statusFilter}
						onValueChange={(value) => (statusFilter = value as 'all' | DigestStatus)}
					>
						<Select.Trigger id="digest-status-filter">
							<span class="capitalize">{statusFilter === 'all' ? 'All statuses' : statusFilter}</span>
						</Select.Trigger>
						<Select.Content>
							<Select.Item value="all">All statuses</Select.Item>
							<Select.Item value="pending">Pending</Select.Item>
							<Select.Item value="processing">Processing</Select.Item>
							<Select.Item value="completed">Completed</Select.Item>
							<Select.Item value="failed">Failed</Select.Item>
						</Select.Content>
					</Select.Root>
				</div>
				<div class="space-y-2">
					<Label for="digest-period-filter">Period</Label>
					<Select.Root
						type="single"
						name="digest-period-filter"
						value={periodFilter}
						onValueChange={(value) => (periodFilter = value as 'all' | DigestPeriod)}
					>
						<Select.Trigger id="digest-period-filter">
							<span class="capitalize">{periodFilter === 'all' ? 'All periods' : periodFilter}</span>
						</Select.Trigger>
						<Select.Content>
							<Select.Item value="all">All periods</Select.Item>
							<Select.Item value="morning">Morning</Select.Item>
							<Select.Item value="noon">Noon</Select.Item>
							<Select.Item value="evening">Evening</Select.Item>
							<Select.Item value="manual">Manual</Select.Item>
						</Select.Content>
					</Select.Root>
				</div>
				<div class="space-y-2">
					<Label for="digest-from-date">From</Label>
					<Input id="digest-from-date" type="date" bind:value={fromDate} />
				</div>
				<div class="space-y-2">
					<Label for="digest-to-date">To</Label>
					<Input id="digest-to-date" type="date" bind:value={toDate} />
				</div>
				<div class="space-y-2">
					<Label for="digest-sort">Sort</Label>
					<div class="flex gap-2">
						<Select.Root
							type="single"
							name="digest-sort"
							value={sortBy}
							onValueChange={(value) =>
								(sortBy = value as 'created_at' | 'total_articles' | 'duration')}
						>
							<Select.Trigger id="digest-sort" class="flex-1">
								<span>
									{sortBy === 'created_at'
										? 'Date'
										: sortBy === 'total_articles'
											? 'Articles'
											: 'Duration'}
								</span>
							</Select.Trigger>
							<Select.Content>
								<Select.Item value="created_at">Date</Select.Item>
								<Select.Item value="total_articles">Articles</Select.Item>
								<Select.Item value="duration">Duration</Select.Item>
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
			<div class="flex flex-wrap items-center gap-2">
				<Button size="sm" variant="outline" onclick={() => setLastDays(7)}>Last 7 days</Button>
				<Button size="sm" variant="outline" onclick={() => setLastDays(30)}>Last 30 days</Button>
				<Button size="sm" variant="outline" onclick={setThisMonth}>This month</Button>
				<Button size="sm" variant="ghost" onclick={clearDateRange}>Clear dates</Button>
				<Button size="sm" variant="ghost" class="ml-auto" onclick={clearFilters}>Reset all filters</Button>
			</div>
			<div class="text-sm text-muted-foreground">
				Showing {visibleDigests.length} digests • {loadedDigests.length} loaded
			</div>
			<div class="flex items-center gap-2">
				<Label class="text-sm text-muted-foreground">View</Label>
				<Button
					size="sm"
					variant={viewMode === 'list' ? 'default' : 'outline'}
					onclick={() => (viewMode = 'list')}
				>
					<List class="mr-2 h-4 w-4" />
					List
				</Button>
				<Button
					size="sm"
					variant={viewMode === 'covers' ? 'default' : 'outline'}
					onclick={() => (viewMode = 'covers')}
				>
					<LayoutGrid class="mr-2 h-4 w-4" />
					Covers
				</Button>
			</div>
		</Card.Header>
	</Card.Root>

	<Card.Root>
		<Card.Content class="p-0">
			{#if digestsQuery.isPending}
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
			{:else if !loadedDigests.length}
				<div class="flex flex-col items-center justify-center py-12 text-center">
					<BookCopy class="h-12 w-12 text-muted-foreground/50" />
					<p class="mt-4 text-lg font-medium">No digests yet</p>
					<p class="text-sm text-muted-foreground">Generate your first digest to populate this history</p>
					<Button onclick={() => triggerMutation.mutate()} class="mt-4" disabled={triggerMutation.isPending}>
						<Play class="mr-2 h-4 w-4" />
						Generate Digest
					</Button>
				</div>
			{:else if !visibleDigests.length}
				<div class="flex flex-col items-center justify-center gap-3 py-12 text-center">
					<Calendar class="h-12 w-12 text-muted-foreground/50" />
					<p class="text-lg font-medium">No digests match this filter set</p>
					<p class="text-sm text-muted-foreground">Try widening the date range or resetting filters.</p>
					<Button variant="outline" onclick={clearFilters}>Reset filters</Button>
				</div>
			{:else if viewMode === 'list'}
				<div class="hidden md:block">
					<Table.Root>
						<Table.Header>
							<Table.Row>
								<Table.Head class="w-[84px]">Cover</Table.Head>
								<Table.Head>Date</Table.Head>
								<Table.Head>Period</Table.Head>
								<Table.Head>Status</Table.Head>
								<Table.Head>Articles</Table.Head>
								<Table.Head>Duration</Table.Head>
								<Table.Head class="w-[320px]">Actions</Table.Head>
							</Table.Row>
						</Table.Header>
						<Table.Body>
							{#each visibleDigests as digest}
								<Table.Row>
									<Table.Cell>
										<div class="h-16 w-12 overflow-hidden rounded border bg-muted">
											{#if getCoverUrl(digest)}
												<img src={getCoverUrl(digest)!} alt="Digest cover" class="h-full w-full object-cover" />
											{:else}
												<div class="flex h-full items-center justify-center text-[10px] text-muted-foreground">
													No cover
												</div>
											{/if}
										</div>
									</Table.Cell>
									<Table.Cell>
										<div class="flex items-center gap-2">
											<Calendar class="h-4 w-4 text-muted-foreground" />
											{formatDate(digest.created_at)}
										</div>
									</Table.Cell>
									<Table.Cell class="capitalize">{digest.period}</Table.Cell>
									<Table.Cell>
										<Badge variant={getDigestStatusBadgeVariant(digest.status)}>{digest.status}</Badge>
									</Table.Cell>
									<Table.Cell>
										{#if digest.total_articles > 0}
											{digest.total_articles}
										{:else}
											<span class="text-muted-foreground">—</span>
										{/if}
									</Table.Cell>
									<Table.Cell>
										{#if getDurationLabel(digest)}
											{getDurationLabel(digest)}
										{:else}
											<span class="text-muted-foreground">—</span>
										{/if}
									</Table.Cell>
									<Table.Cell>
										<div class="flex flex-wrap items-center gap-2">
											{#if digest.status === 'completed'}
												<Button size="sm" variant="outline" onclick={() => openReader(digest)}>
													<Eye class="mr-2 h-4 w-4" />
													Read
												</Button>
												<Button
													size="sm"
													variant="outline"
													onclick={() => triggerDigestPodcast(digest)}
													disabled={isPodcastTriggerPending(digest.id) || !canGeneratePodcast(digest)}
												>
													{#if isPodcastTriggerPending(digest.id)}
														<Loader2 class="mr-2 h-4 w-4 animate-spin" />
														Queuing...
													{:else if isPodcastStatusActive(digest.id)}
														<Loader2 class="mr-2 h-4 w-4 animate-spin" />
														Generating...
													{:else}
														<Mic class="mr-2 h-4 w-4" />
														Generate Podcast
													{/if}
												</Button>
												{#if getPodcastStatusLabel(digest.id)}
													<span class={`text-xs ${isPodcastStatusFailed(digest.id) ? 'text-destructive' : 'text-muted-foreground'}`}>
														{getPodcastStatusLabel(digest.id)}
													</span>
												{/if}
											{/if}
												{#if digest.filename}
													<Button size="sm" variant="outline" onclick={() => downloadDigest(digest, 'epub')} disabled={isDownloadPending(digest, 'epub')}>
														{#if isDownloadPending(digest, 'epub')}
															<Loader2 class="mr-2 h-4 w-4 animate-spin" />
															Preparing...
														{:else}
															<Download class="mr-2 h-4 w-4" />
															EPUB
														{/if}
													</Button>
													{#if supportsFormat(digest, 'pdf')}
														<Button size="sm" variant="outline" onclick={() => downloadDigest(digest, 'pdf')} disabled={isDownloadPending(digest, 'pdf')}>
															{#if isDownloadPending(digest, 'pdf')}
																<Loader2 class="mr-2 h-4 w-4 animate-spin" />
																Preparing...
															{:else}
																<Download class="mr-2 h-4 w-4" />
																PDF
															{/if}
														</Button>
													{/if}
													<Button
														size="sm"
													variant="outline"
													class="text-destructive hover:text-destructive"
													onclick={() => (digestToDelete = digest)}
												>
													<Trash2 class="mr-2 h-4 w-4" />
													Delete
												</Button>
											{/if}
										</div>
									</Table.Cell>
								</Table.Row>
							{/each}
						</Table.Body>
					</Table.Root>
				</div>

				<div class="divide-y md:hidden">
					{#each visibleDigests as digest}
						<div class="space-y-3 p-4">
							<div class="flex items-start gap-3">
								<div class="h-20 w-14 shrink-0 overflow-hidden rounded border bg-muted">
									{#if getCoverUrl(digest)}
										<img src={getCoverUrl(digest)!} alt="Digest cover" class="h-full w-full object-cover" />
									{:else}
										<div class="flex h-full items-center justify-center text-[10px] text-muted-foreground">
											No cover
										</div>
									{/if}
								</div>
								<div class="flex min-w-0 flex-1 items-start justify-between gap-2">
								<div class="min-w-0 flex-1">
									<p class="font-medium capitalize">{digest.period} digest</p>
									<p class="text-sm text-muted-foreground">{formatDate(digest.created_at)}</p>
								</div>
								<Badge variant={getDigestStatusBadgeVariant(digest.status)}>{digest.status}</Badge>
								</div>
							</div>
							<div class="text-xs text-muted-foreground">
								{#if digest.total_articles > 0}
									{digest.total_articles} articles
								{:else}
									No articles
								{/if}
								{#if getDurationLabel(digest)}
									 • {getDurationLabel(digest)}
								{/if}
							</div>
							<div class="flex flex-wrap items-center gap-2">
								{#if digest.status === 'completed'}
									<Button size="sm" variant="outline" onclick={() => openReader(digest)}>
										<Eye class="mr-2 h-4 w-4" />
										Read
									</Button>
									<Button
										size="sm"
										variant="outline"
										onclick={() => triggerDigestPodcast(digest)}
										disabled={isPodcastTriggerPending(digest.id) || !canGeneratePodcast(digest)}
									>
										{#if isPodcastTriggerPending(digest.id)}
											<Loader2 class="mr-2 h-4 w-4 animate-spin" />
											Queuing...
										{:else if isPodcastStatusActive(digest.id)}
											<Loader2 class="mr-2 h-4 w-4 animate-spin" />
											Generating...
										{:else}
											<Mic class="mr-2 h-4 w-4" />
											Generate Podcast
										{/if}
									</Button>
								{/if}
								{#if getPodcastStatusLabel(digest.id)}
									<p class={`text-xs ${isPodcastStatusFailed(digest.id) ? 'text-destructive' : 'text-muted-foreground'}`}>
										{getPodcastStatusLabel(digest.id)}
										{#if isPodcastStatusFailed(digest.id) && getPodcastStatusError(digest.id)}
											: {getPodcastStatusError(digest.id)}
										{/if}
									</p>
								{/if}
									{#if digest.filename}
										<Button size="sm" variant="outline" onclick={() => downloadDigest(digest, 'epub')} disabled={isDownloadPending(digest, 'epub')}>
											{#if isDownloadPending(digest, 'epub')}
												<Loader2 class="mr-2 h-4 w-4 animate-spin" />
												Preparing...
											{:else}
												<Download class="mr-2 h-4 w-4" />
												EPUB
											{/if}
										</Button>
										{#if supportsFormat(digest, 'pdf')}
											<Button size="sm" variant="outline" onclick={() => downloadDigest(digest, 'pdf')} disabled={isDownloadPending(digest, 'pdf')}>
												{#if isDownloadPending(digest, 'pdf')}
													<Loader2 class="mr-2 h-4 w-4 animate-spin" />
													Preparing...
												{:else}
													<Download class="mr-2 h-4 w-4" />
													PDF
												{/if}
											</Button>
										{/if}
										<Button
											size="sm"
										variant="outline"
										class="text-destructive hover:text-destructive"
										onclick={() => (digestToDelete = digest)}
									>
										<Trash2 class="mr-2 h-4 w-4" />
										Delete
									</Button>
								{/if}
							</div>
						</div>
					{/each}
				</div>
			{:else}
				<div class="grid gap-4 p-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
					{#each visibleDigests as digest}
						<div class="rounded-lg border p-3">
							<div class="relative mb-3 aspect-[5/8] overflow-hidden rounded-md border bg-muted">
								{#if getCoverUrl(digest)}
									<img src={getCoverUrl(digest)!} alt="Digest cover" class="h-full w-full object-cover" />
								{:else}
									<div class="flex h-full items-center justify-center text-xs text-muted-foreground">
										No cover
									</div>
								{/if}
								<div class="absolute left-2 top-2">
									<Badge variant={getDigestStatusBadgeVariant(digest.status)}>{digest.status}</Badge>
								</div>
							</div>
							<p class="truncate font-medium capitalize">{digest.period} digest</p>
							<p class="text-xs text-muted-foreground">{formatDate(digest.created_at)}</p>
							<p class="mt-1 text-xs text-muted-foreground">
								{digest.total_articles > 0 ? `${digest.total_articles} articles` : 'No articles'}
								{#if getDurationLabel(digest)}
									{' • '}{getDurationLabel(digest)}
								{/if}
							</p>
							<div class="mt-3 flex flex-wrap gap-2">
								{#if digest.status === 'completed'}
									<Button size="sm" variant="outline" onclick={() => openReader(digest)}>
										<Eye class="mr-2 h-4 w-4" />
										Read
									</Button>
									<Button
										size="sm"
										variant="outline"
										onclick={() => triggerDigestPodcast(digest)}
										disabled={isPodcastTriggerPending(digest.id) || !canGeneratePodcast(digest)}
									>
										{#if isPodcastTriggerPending(digest.id)}
											<Loader2 class="mr-2 h-4 w-4 animate-spin" />
											Queuing...
										{:else if isPodcastStatusActive(digest.id)}
											<Loader2 class="mr-2 h-4 w-4 animate-spin" />
											Generating...
										{:else}
											<Mic class="mr-2 h-4 w-4" />
											Podcast
										{/if}
									</Button>
								{/if}
								{#if getPodcastStatusLabel(digest.id)}
									<p class={`w-full text-xs ${isPodcastStatusFailed(digest.id) ? 'text-destructive' : 'text-muted-foreground'}`}>
										{getPodcastStatusLabel(digest.id)}
									</p>
								{/if}
									{#if digest.filename}
										<Button size="sm" variant="outline" onclick={() => downloadDigest(digest, 'epub')} disabled={isDownloadPending(digest, 'epub')}>
											{#if isDownloadPending(digest, 'epub')}
												<Loader2 class="mr-2 h-4 w-4 animate-spin" />
												Preparing...
											{:else}
												<Download class="mr-2 h-4 w-4" />
												EPUB
											{/if}
										</Button>
										{#if supportsFormat(digest, 'pdf')}
											<Button size="sm" variant="outline" onclick={() => downloadDigest(digest, 'pdf')} disabled={isDownloadPending(digest, 'pdf')}>
												{#if isDownloadPending(digest, 'pdf')}
													<Loader2 class="mr-2 h-4 w-4 animate-spin" />
													Preparing...
												{:else}
													<Download class="mr-2 h-4 w-4" />
													PDF
												{/if}
											</Button>
										{/if}
										<Button
										size="sm"
										variant="outline"
										class="text-destructive hover:text-destructive"
										onclick={() => (digestToDelete = digest)}
									>
										<Trash2 class="mr-2 h-4 w-4" />
										Delete
									</Button>
								{/if}
							</div>
						</div>
					{/each}
				</div>
			{/if}

			{#if hasMore}
				<div class="border-t p-4">
					<Button
						variant="outline"
						class="w-full"
						onclick={loadMore}
						disabled={digestsQuery.isFetching}
					>
						{#if digestsQuery.isFetching}
							<Loader2 class="mr-2 h-4 w-4 animate-spin" />
							Loading more...
						{:else}
							Load 20 more
						{/if}
					</Button>
				</div>
			{/if}
		</Card.Content>
	</Card.Root>
</div>

<AlertDialog.Root open={!!digestToDelete} onOpenChange={(open) => !open && (digestToDelete = null)}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Delete Digest</AlertDialog.Title>
			<AlertDialog.Description>
				Are you sure you want to delete the {digestToDelete?.period} digest from{' '}
				{digestToDelete ? formatShortDate(digestToDelete.created_at) : ''}? This will also remove
				the EPUB file.
			</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Cancel</AlertDialog.Cancel>
			<AlertDialog.Action
				onclick={() => digestToDelete?.filename && deleteMutation.mutate(digestToDelete.filename)}
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
