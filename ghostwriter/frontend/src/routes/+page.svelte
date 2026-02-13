<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { api } from '$lib/api';
	import * as Card from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { Progress } from '$lib/components/ui/progress';
	import { formatUTCDate, parseUTC } from '$lib/utils/date';
	import { downloadDigestFile, getDigestStatusBadgeVariant } from '$lib/utils/digest';
	import { toast } from 'svelte-sonner';
	import {
		Activity,
		Rss,
		BookCopy,
		Clock,
		Download,
		Play,
		Loader2,
		AlertCircle,
		CheckCircle2,
		Calendar
	} from 'lucide-svelte';

	// Queries
	const healthQuery = createQuery(() => ({
		queryKey: ['health'],
		queryFn: () => api.getHealth(),
		refetchInterval: 30000 // Refresh every 30s
	}));

	const configQuery = createQuery(() => ({
		queryKey: ['config'],
		queryFn: () => api.getPublicConfig()
	}));

	const feedsQuery = createQuery(() => ({
		queryKey: ['feeds'],
		queryFn: () => api.getFeeds()
	}));

	const digestsQuery = createQuery(() => ({
		queryKey: ['digests', { limit: 5 }],
		queryFn: () => api.getDigests({ limit: 5 })
	}));

	function getStartOfWeek(): string {
		const now = new Date();
		const day = now.getDay();
		const diff = day === 0 ? 6 : day - 1; // Monday as start of week
		const monday = new Date(now);
		monday.setDate(now.getDate() - diff);
		monday.setHours(0, 0, 0, 0);
		return monday.toISOString();
	}

	const weeklyDigestsQuery = createQuery(() => ({
		queryKey: ['digests', { since: getStartOfWeek(), status: 'completed', limit: 100 }],
		queryFn: () =>
			api.getDigests({ since: getStartOfWeek(), status: 'completed', limit: 100 })
	}));

	const schedulesQuery = createQuery(() => ({
		queryKey: ['schedules'],
		queryFn: () => api.getSchedules()
	}));

	// State
	let triggering = $state(false);

	// Computed
	const activeFeedsCount = $derived(feedsQuery.data?.filter((f) => f.is_active).length ?? 0);
	const latestDigest = $derived(digestsQuery.data?.[0]);
	const processingDigest = $derived(digestsQuery.data?.find((d) => d.status === 'processing'));

	// Get next scheduled run
	const nextScheduledRun = $derived.by(() => {
		const schedules = schedulesQuery.data;
		if (!schedules) return null;

		const enabledSchedules = schedules.filter((s) => s.enabled && s.next_run_at);
		if (enabledSchedules.length === 0) return null;

		const sorted = enabledSchedules.sort(
			(a, b) => new Date(a.next_run_at!).getTime() - new Date(b.next_run_at!).getTime()
		);
		return sorted[0];
	});

	async function handleTriggerDigest() {
		triggering = true;
		try {
			const result = await api.triggerDigest();
			toast.success('Digest generation started', {
				description: result.message
			});
			// Refetch digests to show the new processing one
			digestsQuery.refetch();
		} catch (err) {
			toast.error('Failed to trigger digest', {
				description: err instanceof Error ? err.message : 'Unknown error'
			});
		} finally {
			triggering = false;
		}
	}

	function formatDate(dateStr: string): string {
		return formatUTCDate(dateStr, {
			month: 'short',
			day: 'numeric',
			hour: 'numeric',
			minute: '2-digit'
		});
	}

	function formatRelativeTime(dateStr: string): string {
		const date = parseUTC(dateStr);
		const now = new Date();
		const diff = date.getTime() - now.getTime();

		if (diff < 0) {
			return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
		}

		const hours = Math.floor(diff / (1000 * 60 * 60));
		const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));

		if (hours > 0) return `in ${hours}h ${minutes}m`;
		return `in ${minutes}m`;
	}

	async function downloadDigest(filename: string) {
		try {
			await downloadDigestFile(filename);
		} catch (err) {
			const message = err instanceof Error ? err.message : 'Unknown error';
			toast.error('Failed to download digest', { description: message });
		}
	}
</script>

<svelte:head>
	<title>Dashboard - Ghostwriter</title>
</svelte:head>

<div class="space-y-6">
	<div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
		<div>
			<h1 class="text-2xl font-bold tracking-tight">Dashboard</h1>
			<p class="text-muted-foreground">Monitor jobs, trigger digests, and review outcomes</p>
		</div>
		<div class="flex flex-wrap gap-2">
			<Button onclick={handleTriggerDigest} disabled={triggering || !!processingDigest}>
				{#if triggering}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					Starting...
				{:else if processingDigest}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					Processing...
				{:else}
					<Play class="mr-2 h-4 w-4" />
					Generate Digest
				{/if}
			</Button>
			{#if latestDigest?.filename}
				<Button variant="outline" onclick={() => downloadDigest(latestDigest.filename!)}>
					<Download class="mr-2 h-4 w-4" />
					Download Latest
				</Button>
			{/if}
		</div>
	</div>

	{#if healthQuery.error}
		<Card.Root class="border-destructive/40 bg-destructive/5">
			<Card.Content class="flex items-center gap-3 py-4">
				<AlertCircle class="h-5 w-5 text-destructive" />
				<div>
					<p class="font-medium text-destructive">Server appears offline</p>
					<p class="text-sm text-muted-foreground">
						Some actions may fail until connectivity is restored.
					</p>
				</div>
			</Card.Content>
		</Card.Root>
	{:else if processingDigest}
		<Card.Root class="border-info/30 bg-info/10">
			<Card.Content class="space-y-4 py-4">
				<div class="flex items-center gap-2">
					<Loader2 class="h-4 w-4 animate-spin text-info" />
					<p class="font-medium text-info">
						Generating {processingDigest.period} digest • {processingDigest.stage ?? 'Processing'}
					</p>
				</div>
				<div class="grid gap-3 md:grid-cols-2">
					<div class="space-y-2">
						<div class="flex justify-between text-sm">
							<span>Feeds</span>
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
							<span>Articles</span>
							<span>{processingDigest.articles_enriched}/{processingDigest.total_articles}</span>
						</div>
						<Progress
							value={processingDigest.total_articles > 0
								? (processingDigest.articles_enriched / processingDigest.total_articles) * 100
								: 0}
						/>
					</div>
				</div>
			</Card.Content>
		</Card.Root>
	{/if}

	<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
		<Card.Root>
			<Card.Header class="flex flex-row items-center justify-between space-y-0 pb-2">
				<Card.Title class="text-sm font-medium">Server Status</Card.Title>
				<Activity class="h-4 w-4 text-muted-foreground" />
			</Card.Header>
			<Card.Content>
				{#if healthQuery.isPending}
					<Skeleton class="h-7 w-20" />
				{:else if healthQuery.error}
					<div class="flex items-center gap-2 text-destructive">
						<AlertCircle class="h-4 w-4" />
						<span class="text-lg font-bold">Offline</span>
					</div>
				{:else}
					<div class="flex items-center gap-2 text-success">
						<CheckCircle2 class="h-4 w-4" />
						<span class="text-lg font-bold">Online</span>
					</div>
					<p class="text-xs text-muted-foreground">v{healthQuery.data?.version}</p>
				{/if}
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header class="flex flex-row items-center justify-between space-y-0 pb-2">
				<Card.Title class="text-sm font-medium">Active Feeds</Card.Title>
				<Rss class="h-4 w-4 text-muted-foreground" />
			</Card.Header>
			<Card.Content>
				{#if feedsQuery.isPending}
					<Skeleton class="h-7 w-12" />
				{:else}
					<div class="text-2xl font-bold">{activeFeedsCount}</div>
					<p class="text-xs text-muted-foreground">{feedsQuery.data?.length ?? 0} total feeds</p>
				{/if}
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header class="flex flex-row items-center justify-between space-y-0 pb-2">
				<Card.Title class="text-sm font-medium">Recent Digests</Card.Title>
				<BookCopy class="h-4 w-4 text-muted-foreground" />
			</Card.Header>
			<Card.Content>
				{#if weeklyDigestsQuery.isPending}
					<Skeleton class="h-7 w-12" />
				{:else}
					<div class="text-2xl font-bold">{weeklyDigestsQuery.data?.length ?? 0}</div>
					<p class="text-xs text-muted-foreground">completed this week</p>
				{/if}
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header class="flex flex-row items-center justify-between space-y-0 pb-2">
				<Card.Title class="text-sm font-medium">Next Scheduled</Card.Title>
				<Clock class="h-4 w-4 text-muted-foreground" />
			</Card.Header>
			<Card.Content>
				{#if schedulesQuery.isPending}
					<Skeleton class="h-7 w-24" />
				{:else if nextScheduledRun}
					<div class="text-lg font-bold">{formatRelativeTime(nextScheduledRun.next_run_at!)}</div>
					<p class="text-xs text-muted-foreground capitalize">{nextScheduledRun.period} digest</p>
				{:else}
					<div class="text-lg font-bold text-muted-foreground">Not scheduled</div>
					<p class="text-xs text-muted-foreground">No active schedules</p>
				{/if}
			</Card.Content>
		</Card.Root>
	</div>

	<div class="grid gap-4 md:grid-cols-2">
		<Card.Root>
			<Card.Header>
				<Card.Title>AI Configuration</Card.Title>
				<Card.Description>Current provider and model configuration</Card.Description>
			</Card.Header>
			<Card.Content>
				{#if configQuery.isPending}
					<div class="space-y-2">
						<Skeleton class="h-4 w-32" />
						<Skeleton class="h-4 w-48" />
					</div>
				{:else if configQuery.data}
					<div class="space-y-1">
						<div class="flex items-center gap-2">
							<span class="text-sm text-muted-foreground">Provider:</span>
							<span class="font-medium">{configQuery.data.ai_provider}</span>
						</div>
						<div class="flex items-center gap-2">
							<span class="text-sm text-muted-foreground">Model:</span>
							<span class="font-medium">{configQuery.data.ai_model}</span>
						</div>
					</div>
				{/if}
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header>
				<Card.Title>Latest Run</Card.Title>
				<Card.Description>Most recent digest attempt</Card.Description>
			</Card.Header>
			<Card.Content>
				{#if digestsQuery.isPending}
					<div class="space-y-2">
						<Skeleton class="h-4 w-40" />
						<Skeleton class="h-4 w-28" />
					</div>
				{:else if latestDigest}
					<div class="space-y-2">
						<div class="flex items-center gap-2">
							<Badge variant={getDigestStatusBadgeVariant(latestDigest.status)}>
								{latestDigest.status}
							</Badge>
							<span class="text-sm text-muted-foreground capitalize">{latestDigest.period} digest</span>
						</div>
						<p class="text-sm text-muted-foreground">{formatDate(latestDigest.created_at)}</p>
					</div>
				{:else}
					<p class="text-sm text-muted-foreground">No digest runs yet.</p>
				{/if}
			</Card.Content>
		</Card.Root>
	</div>

	<Card.Root>
		<Card.Header>
			<Card.Title>Recent Digests</Card.Title>
			<Card.Description>Your latest generated digests</Card.Description>
		</Card.Header>
		<Card.Content>
			{#if digestsQuery.isPending}
				<div class="space-y-3">
					{#each [1, 2, 3] as _}
						<div class="flex items-center gap-4">
							<Skeleton class="h-10 w-10 rounded" />
							<div class="flex-1 space-y-2">
								<Skeleton class="h-4 w-32" />
								<Skeleton class="h-3 w-24" />
							</div>
							<Skeleton class="h-8 w-20" />
						</div>
					{/each}
				</div>
			{:else if !digestsQuery.data?.length}
				<div class="flex flex-col items-center justify-center py-8 text-center">
					<BookCopy class="h-10 w-10 text-muted-foreground/50" />
					<p class="mt-2 text-sm text-muted-foreground">No digests yet</p>
					<p class="text-xs text-muted-foreground">Generate your first digest to get started</p>
				</div>
			{:else}
				<div class="space-y-3">
					{#each digestsQuery.data as digest}
						<div class="flex items-center gap-4 rounded-lg border p-3 transition-colors hover:bg-muted/50">
							<div class="flex h-10 w-10 items-center justify-center rounded bg-primary/10 text-primary">
								<Calendar class="h-5 w-5" />
							</div>
							<div class="min-w-0 flex-1">
								<p class="truncate font-medium capitalize">{digest.period} Digest</p>
								<p class="text-sm text-muted-foreground">
									{formatDate(digest.created_at)}
									{#if digest.total_articles > 0}
										• {digest.total_articles} articles
									{/if}
								</p>
							</div>
							<div class="flex items-center gap-2">
								<Badge variant={getDigestStatusBadgeVariant(digest.status)}>
									{digest.status}
								</Badge>
								{#if digest.filename && digest.status === 'completed'}
									<Button
										variant="ghost"
										size="icon"
										onclick={() => downloadDigest(digest.filename!)}
									>
										<Download class="h-4 w-4" />
									</Button>
								{/if}
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</Card.Content>
		<Card.Footer>
			<Button variant="outline" class="w-full" href="/digests">
				View All Digests
			</Button>
		</Card.Footer>
	</Card.Root>
</div>
