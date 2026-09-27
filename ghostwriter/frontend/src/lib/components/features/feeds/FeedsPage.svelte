<script lang="ts">
	import { createQuery, createMutation, useQueryClient } from '@tanstack/svelte-query';
	import { api, ApiError, type Feed, type FeedCreate, type FeedUpdate } from '$lib/api';
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
	import { formatUTCDate } from '$lib/utils/date';
	import { toast } from 'svelte-sonner';
	import {
		Plus,
		Trash2,
		Pencil,
		Search,
		Rss,
		ExternalLink,
		MoreHorizontal,
		Loader2,
		RotateCcw
	} from 'lucide-svelte';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';

	const queryClient = useQueryClient();
	type ConflictEntry = { id: number; message: string; action: string; retry: () => void; pending: boolean };
	let conflicts = $state<ConflictEntry[]>([]);
	let nextConflictId = 0;
	function finishConflict(id?: number) {
		if (id !== undefined) conflicts = conflicts.filter((entry) => entry.id !== id);
	}
	function releaseConflict(id?: number) {
		if (id !== undefined) conflicts = conflicts.map((entry) => entry.id === id ? { ...entry, pending: false } : entry);
	}
	function offerConflict(err: Error, action: string, retry: (version: number, conflict: number) => void,
		restore?: (version: number, conflict: number) => void, id?: number, closeOrigin?: () => void,
		feedIdentity?: Pick<FeedCreate, 'title' | 'url'>): boolean {
		if (!(err instanceof ApiError) || (err.status !== 409 && err.status !== 428)) return false;
		const detail = typeof err.error.detail === 'string' ? null : err.error.detail;
		const version = detail?.current?.version;
		if (typeof version !== 'number') return false;
		// A dismissed operation cannot be resurrected by an old in-flight response.
		if (id !== undefined && !conflicts.some((entry) => entry.id === id)) return true;
		const current = detail?.current;
		const identity = feedIdentity ? `Feed: ${feedIdentity.title} (${feedIdentity.url}). ` : '';
		const currentDescription = current?.kind === 'tombstone'
			? 'The server currently has this feed deleted.'
			: `Server title: ${current?.title ?? 'unknown'}, mode: ${current?.mode ?? 'unknown'}, active: ${current?.is_active ? 'yes' : 'no'}, max articles: ${current?.max_articles ?? 'unknown'}.`;
		const message = `${identity}This feed changed on the server (version ${version}). ${currentDescription} Review it before ${action}.`;
		const restoring = current?.kind === 'tombstone' && restore;
		const conflictId = id ?? ++nextConflictId;
		const entry: ConflictEntry = {
			id: conflictId, message,
			action: restoring ? 'Restore feed with my changes' : 'Retry with current server version',
			pending: false,
			retry: () => {
				conflicts = conflicts.map((item) => item.id === conflictId ? { ...item, pending: true } : item);
				(restoring || retry)(version, conflictId);
			}
		};
		conflicts = id === undefined ? [...conflicts, entry] :
			conflicts.map((item) => item.id === conflictId ? entry : item);
		closeOrigin?.();
		queryClient.invalidateQueries({ queryKey: ['feeds'] });
		return true;
	}

	type EditVariables = { feed: Feed; data: FeedUpdate; conflict?: number; editSession?: number; activeSnapshot?: Partial<Feed> };
	function mergedProposal(base: FeedCreate, proposed: FeedUpdate, current?: Partial<Feed>): FeedCreate {
		return {
			url: base.url, title: proposed.title ?? current?.title ?? base.title,
			mode: proposed.mode ?? current?.mode ?? base.mode,
			is_active: proposed.is_active ?? current?.is_active ?? base.is_active,
			max_articles: proposed.max_articles ?? current?.max_articles ?? base.max_articles
		};
	}
	function offerEditConflict(err: Error, action: string, variables: EditVariables,
		retry: (version: number, conflict: number, activeSnapshot?: Partial<Feed>) => void): boolean {
		const { feed, data } = variables;
		const detail = err instanceof ApiError && typeof err.error.detail !== 'string' ? err.error.detail : null;
		const activeSnapshot = detail?.current?.kind === 'feed'
			? { ...variables.activeSnapshot, ...detail.current } : variables.activeSnapshot;
		const proposed = mergedProposal(feed, data, activeSnapshot);
		return offerConflict(err, action,
			(version, conflict) => retry(version, conflict, activeSnapshot),
			(version, conflict) => createFeedMutation.mutate({ data: proposed, version, conflict,
				origin: 'restore', partialData: data, activeSnapshot }),
			variables.conflict,
			() => {
				if (variables.editSession !== undefined && variables.editSession === editSession &&
					feedToEdit?.id === feed.id) editDialogOpen = false;
			}, feed);
	}

	// Queries
	const feedsQuery = createQuery(() => ({
		queryKey: ['feeds'],
		queryFn: () => api.getFeeds()
	}));

	// Mutations
	const createFeedMutation = createMutation(() => ({
		mutationFn: ({ data, version, existingId }: { data: FeedCreate; version?: number; conflict?: number; existingId?: string; origin: 'add' | 'restore'; addSession?: number; partialData?: FeedUpdate; activeSnapshot?: Partial<Feed> }) => {
			if (existingId && version !== undefined) {
				const { url: _url, ...fields } = data;
				return api.updateFeed(existingId, fields, version);
			}
			return api.createFeed(data, version);
		},
			onSuccess: (_data, variables) => {
			queryClient.invalidateQueries({ queryKey: ['feeds'] });
			toast.success('Feed saved successfully');
			if (variables.origin === 'add' && variables.addSession === addSession) {
				addDialogOpen = false;
				resetForm();
			}
			finishConflict(variables.conflict);
		},
		onError: (err: Error, variables) => {
			const detail = err instanceof ApiError && typeof err.error.detail !== 'string' ? err.error.detail : null;
			if (detail?.current?.kind === 'tombstone' &&
				offerConflict(err, 'restoring it', (version, conflict) => createFeedMutation.mutate({ ...variables, existingId: undefined, version, conflict }),
					(version, conflict) => createFeedMutation.mutate({ ...variables, existingId: undefined, version, conflict }),
					variables.conflict,
					() => { if (variables.origin === 'add' && variables.addSession === addSession) addDialogOpen = false; },
					variables.data)) return;
			if (variables.conflict !== undefined && detail?.current?.kind === 'feed' &&
				typeof detail.current.id === 'string') {
				const existingId = detail.current.id;
				const activeSnapshot = { ...variables.activeSnapshot, ...detail.current };
				const data = variables.partialData
					? mergedProposal(variables.data, variables.partialData, activeSnapshot)
					: variables.data;
				if (offerConflict(err, 'saving your proposed settings', (version, conflict) =>
					createFeedMutation.mutate({ ...variables, data, activeSnapshot, existingId, version, conflict }),
					undefined, variables.conflict, undefined, variables.data)) return;
			}
			releaseConflict(variables.conflict);
			toast.error('Failed to create feed', {
				description: err.message ?? 'Unknown error'
			});
		}
	}));

	const deleteFeedMutation = createMutation(() => ({
		mutationFn: (feed: Feed & { conflict?: number; deleteSession?: number }) => api.deleteFeed(feed.id, feed.version),
		onSuccess: (_data, variables) => {
			queryClient.invalidateQueries({ queryKey: ['feeds'] });
			toast.success('Feed deleted');
			if (variables.deleteSession === deleteSession && feedToDelete?.id === variables.id)
				feedToDelete = null;
			finishConflict(variables.conflict);
		},
		onError: (err: Error, feed) => {
			if (offerConflict(err, 'deleting it', (version, conflict) => deleteFeedMutation.mutate({ ...feed, version, conflict }),
				undefined, feed.conflict,
				() => {
					if (feed.deleteSession === deleteSession && feedToDelete?.id === feed.id)
						feedToDelete = null;
				}, feed)) return;
			releaseConflict(feed.conflict);
			toast.error('Failed to delete feed', {
				description: err.message ?? 'Unknown error'
			});
		}
	}));

	const updateFeedMutation = createMutation(() => ({
		mutationFn: ({ feed, data }: EditVariables) => api.updateFeed(feed.id, data, feed.version),
		onSuccess: (_data, variables) => {
			queryClient.invalidateQueries({ queryKey: ['feeds'] });
			toast.success('Feed updated successfully');
			if (variables.editSession !== undefined && variables.editSession === editSession &&
				feedToEdit?.id === variables.feed.id) {
				editDialogOpen = false;
				feedToEdit = null;
			}
			finishConflict(variables.conflict);
		},
		onError: (err: Error, variables) => {
			if (offerEditConflict(err, 'saving your edit', variables, (version, conflict, activeSnapshot) =>
				updateFeedMutation.mutate({ ...variables, conflict, activeSnapshot, feed: { ...variables.feed, version } }))) return;
			releaseConflict(variables.conflict);
			toast.error('Failed to update feed', {
				description: err.message ?? 'Unknown error'
			});
		}
	}));

	const toggleFeedMutation = createMutation(() => ({
		mutationFn: ({ feed, data }: EditVariables) => api.updateFeed(feed.id, data, feed.version),
		onSuccess: (_data, variables) => {
			queryClient.invalidateQueries({ queryKey: ['feeds'] });
			toast.success(variables.data.is_active ? 'Feed activated' : 'Feed paused');
			finishConflict(variables.conflict);
		},
		onError: (err: Error, variables) => {
			if (offerEditConflict(err, 'changing its status', variables, (version, conflict, activeSnapshot) =>
				toggleFeedMutation.mutate({ ...variables, conflict, activeSnapshot, feed: { ...variables.feed, version } }))) return;
			releaseConflict(variables.conflict);
			toast.error('Failed to update feed status', {
				description: err.message ?? 'Unknown error'
			});
		},
		onSettled: () => {
			updatingFeedId = null;
		}
	}));

	const clearSeenMutation = createMutation(() => ({
		mutationFn: (id: string) => api.clearSeenArticles(id),
		onSuccess: (data) => {
			toast.success(`Cleared ${data.cleared_count} seen articles`);
			feedToClearSeen = null;
		},
		onError: (err: Error) => {
			toast.error('Failed to clear seen articles', {
				description: err.message ?? 'Unknown error'
			});
		}
	}));

	// State
	let searchQuery = $state('');
	let addDialogOpen = $state(false);
	let editDialogOpen = $state(false);
	let addSession = 0;
	function openAddDialog() {
		addSession += 1;
		addDialogOpen = true;
	}
	let editSession = 0;
	let deleteSession = 0;
	let feedToDelete = $state<Feed | null>(null);
	let feedToEdit = $state<Feed | null>(null);
	let feedToClearSeen = $state<Feed | null>(null);
	let updatingFeedId = $state<string | null>(null);
	let statusFilter = $state<'all' | 'active' | 'paused'>('all');
	let modeFilter = $state<'all' | 'raw' | 'summarize'>('all');
	let selectedFeedIds = $state<string[]>([]);
	let bulkActionPending = $state(false);
	let bulkDeleteConfirmOpen = $state(false);

	// Form state (for add)
	let formUrl = $state('');
	let formTitle = $state('');
	let formMode = $state<'raw' | 'summarize'>('raw');
	let formMaxArticles = $state(5);

	// Edit form state
	let editTitle = $state('');
	let editMode = $state<'raw' | 'summarize'>('raw');
	let editMaxArticles = $state(5);
	let editIsActive = $state(true);

	// Filtered feeds
	const filteredFeeds = $derived.by(() => {
		const feeds = (feedsQuery.data ?? []).filter((f) => !f.url.startsWith('synthetic://'));
		const q = searchQuery.trim().toLowerCase();

		return feeds.filter((feed) => {
			const matchesSearch =
				q.length === 0 ||
				feed.title.toLowerCase().includes(q) ||
				feed.url.toLowerCase().includes(q);
			const matchesStatus =
				statusFilter === 'all' ||
				(statusFilter === 'active' ? feed.is_active : !feed.is_active);
			const matchesMode = modeFilter === 'all' || feed.mode === modeFilter;
			return matchesSearch && matchesStatus && matchesMode;
		});
	});

	const selectedFeedsCount = $derived(selectedFeedIds.length);
	const allFilteredSelected = $derived(
		filteredFeeds.length > 0 && filteredFeeds.every((feed) => selectedFeedIds.includes(feed.id))
	);

	$effect(() => {
		const availableIds = new Set(filteredFeeds.map((feed) => feed.id));
		const nextSelected = selectedFeedIds.filter((id) => availableIds.has(id));
		const unchanged =
			nextSelected.length === selectedFeedIds.length &&
			nextSelected.every((id, index) => id === selectedFeedIds[index]);
		if (unchanged) return;
		selectedFeedIds = nextSelected;
	});

	function resetForm() {
		formUrl = '';
		formTitle = '';
		formMode = 'raw';
		formMaxArticles = 5;
	}

	function handleAddFeed(e: Event) {
		e.preventDefault();
		const normalizedUrl = formUrl.trim();
		if (!isValidFeedUrl(normalizedUrl)) {
			toast.error('Invalid feed URL', {
				description: 'Use a valid http or https URL'
			});
			return;
		}
		const maxArticles = clampMaxArticles(formMaxArticles);
		createFeedMutation.mutate({ origin: 'add', addSession, data: {
			url: normalizedUrl,
			title: formTitle.trim() || normalizedUrl,
			mode: formMode,
			max_articles: maxArticles,
			is_active: true
		} });
	}

	function handleDeleteFeed(feed: Feed) {
		deleteSession += 1;
		feedToDelete = feed;
	}

	function confirmDelete() {
		if (feedToDelete) {
			deleteFeedMutation.mutate({ ...feedToDelete, deleteSession });
		}
	}

	function handleClearSeen(feed: Feed) {
		feedToClearSeen = feed;
	}

	function confirmClearSeen() {
		if (feedToClearSeen) {
			clearSeenMutation.mutate(feedToClearSeen.id);
		}
	}

	function handleEditFeed(feed: Feed) {
		editSession += 1;
		feedToEdit = feed;
		editTitle = feed.title;
		editMode = feed.mode as 'raw' | 'summarize';
		editMaxArticles = feed.max_articles;
		editIsActive = feed.is_active;
		editDialogOpen = true;
	}

	function handleUpdateFeed(e: Event) {
		e.preventDefault();
		if (!feedToEdit) return;
		const title = editTitle.trim();
		if (!title) {
			toast.error('Title is required');
			return;
		}
		const maxArticles = clampMaxArticles(editMaxArticles);
		updateFeedMutation.mutate({
			feed: feedToEdit,
			editSession,
			data: {
				title,
				mode: editMode,
				max_articles: maxArticles,
				is_active: editIsActive
			}
		});
	}

	function handleToggleFeed(feed: Feed) {
		if (toggleFeedMutation.isPending) return;
		updatingFeedId = feed.id;
		toggleFeedMutation.mutate({
			feed,
			data: {
				is_active: !feed.is_active
			}
		});
	}

	function formatDate(dateStr: string): string {
		return formatUTCDate(dateStr, {
			month: 'short',
			day: 'numeric',
			year: 'numeric'
		});
	}

	function isValidFeedUrl(value: string): boolean {
		try {
			const parsed = new URL(value);
			return parsed.protocol === 'http:' || parsed.protocol === 'https:';
		} catch {
			return false;
		}
	}

	function clampMaxArticles(value: number): number {
		const numeric = Number.isFinite(value) ? value : 5;
		return Math.max(0, Math.min(50, Math.round(numeric)));
	}

	function toggleFeedSelection(feedId: string, checked: boolean) {
		if (checked) {
			selectedFeedIds = [...new Set([...selectedFeedIds, feedId])];
			return;
		}
		selectedFeedIds = selectedFeedIds.filter((id) => id !== feedId);
	}

	function toggleSelectAllFiltered(checked: boolean) {
		if (checked) {
			selectedFeedIds = filteredFeeds.map((feed) => feed.id);
			return;
		}
		selectedFeedIds = [];
	}

	async function applyBulkStatus(isActive: boolean) {
		if (selectedFeedIds.length === 0) return;
		bulkActionPending = true;
		try {
			const selected = (feedsQuery.data ?? []).filter((feed) => selectedFeedIds.includes(feed.id));
			const results = await Promise.allSettled(
				selected.map((feed) => api.updateFeed(feed.id, { is_active: isActive }, feed.version))
			);
			const successCount = results.filter((result) => result.status === 'fulfilled').length;
			if (successCount > 0) {
				toast.success(`${successCount} feed${successCount === 1 ? '' : 's'} updated`);
				queryClient.invalidateQueries({ queryKey: ['feeds'] });
			}
			const failureCount = results.length - successCount;
			if (failureCount > 0) {
				results.forEach((result, index) => {
					if (result.status !== 'rejected') return;
					offerEditConflict(result.reason, 'changing its status',
						{ feed: selected[index], data: { is_active: isActive } },
						(version, conflict, activeSnapshot) => toggleFeedMutation.mutate({
							conflict, activeSnapshot, feed: { ...selected[index], version },
							data: { is_active: isActive }
						}));
				});
				toast.error(`${failureCount} feed update${failureCount === 1 ? '' : 's'} failed`);
			}
		} finally {
			bulkActionPending = false;
		}
	}

	async function confirmBulkDelete() {
		if (selectedFeedIds.length === 0) return;
		bulkActionPending = true;
		try {
			const selected = (feedsQuery.data ?? []).filter((feed) => selectedFeedIds.includes(feed.id));
			const results = await Promise.allSettled(selected.map((feed) => api.deleteFeed(feed.id, feed.version)));
			const successCount = results.filter((result) => result.status === 'fulfilled').length;
			if (successCount > 0) {
				toast.success(`${successCount} feed${successCount === 1 ? '' : 's'} deleted`);
				queryClient.invalidateQueries({ queryKey: ['feeds'] });
				selectedFeedIds = selected.filter((_, index) => results[index].status === 'rejected').map((feed) => feed.id);
			}
			const failureCount = results.length - successCount;
			if (failureCount > 0) {
				results.forEach((result, index) => {
					if (result.status !== 'rejected') return;
					offerConflict(result.reason, 'deleting it', (version, conflict) =>
						deleteFeedMutation.mutate({ ...selected[index], version, conflict }),
						undefined, undefined, undefined, selected[index]);
				});
				toast.error(`${failureCount} feed deletion${failureCount === 1 ? '' : 's'} failed`);
			}
		} finally {
			bulkActionPending = false;
			bulkDeleteConfirmOpen = false;
		}
	}
</script>

<svelte:head>
	<title>Feeds - Ghostwriter</title>
</svelte:head>

<div class="space-y-6 min-w-0">
	{#each conflicts as conflict (conflict.id)}
		<div role="alert" class="rounded-lg border border-amber-500 p-4 space-y-2">
			<p>{conflict.message}</p>
			<Button type="button" variant="outline" disabled={conflict.pending} onclick={conflict.retry}>{conflict.action}</Button>
			<Button type="button" variant="ghost" onclick={() => finishConflict(conflict.id)}>Dismiss</Button>
		</div>
	{/each}
	<div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
		<div>
			<h1 class="text-2xl font-bold tracking-tight">Feeds</h1>
			<p class="text-muted-foreground">Manage your RSS and Atom feed subscriptions</p>
		</div>
		<Button onclick={openAddDialog}>
			<Plus class="mr-2 h-4 w-4" />
			Add Feed
		</Button>
	</div>

	<!-- Search -->
	<Card.Root>
		<Card.Content class="pt-6">
			<div class="space-y-4">
				<div class="relative">
					<Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
					<Input
						placeholder="Search feeds..."
						bind:value={searchQuery}
						class="pl-9"
					/>
				</div>
				<div class="flex flex-wrap items-center gap-2">
					<Select.Root
						type="single"
						name="status-filter"
						value={statusFilter}
						onValueChange={(value) => (statusFilter = value as 'all' | 'active' | 'paused')}
					>
						<Select.Trigger class="w-[140px]">
							<span class="capitalize">
								{statusFilter === 'all' ? 'All statuses' : statusFilter}
							</span>
						</Select.Trigger>
						<Select.Content>
							<Select.Item value="all">All statuses</Select.Item>
							<Select.Item value="active">Active</Select.Item>
							<Select.Item value="paused">Paused</Select.Item>
						</Select.Content>
					</Select.Root>
					<Select.Root
						type="single"
						name="mode-filter"
						value={modeFilter}
						onValueChange={(value) => (modeFilter = value as 'all' | 'raw' | 'summarize')}
					>
						<Select.Trigger class="w-[150px]">
							<span class="capitalize">{modeFilter === 'all' ? 'All modes' : modeFilter}</span>
						</Select.Trigger>
						<Select.Content>
							<Select.Item value="all">All modes</Select.Item>
							<Select.Item value="raw">Raw</Select.Item>
							<Select.Item value="summarize">Summarize</Select.Item>
						</Select.Content>
					</Select.Root>
					<p class="ml-auto text-sm text-muted-foreground">
						{filteredFeeds.length} visible
						{#if statusFilter !== 'all' || modeFilter !== 'all' || searchQuery.trim()}
							<span> • filtered</span>
						{/if}
					</p>
				</div>
			</div>
		</Card.Content>
	</Card.Root>

	{#if selectedFeedsCount > 0}
		<Card.Root>
			<Card.Content class="flex flex-wrap items-center gap-2 py-4">
				<p class="mr-2 text-sm font-medium">
					{selectedFeedsCount} selected
				</p>
				<Button
					size="sm"
					variant="outline"
					onclick={() => applyBulkStatus(true)}
					disabled={bulkActionPending}
				>
					Activate
				</Button>
				<Button
					size="sm"
					variant="outline"
					onclick={() => applyBulkStatus(false)}
					disabled={bulkActionPending}
				>
					Pause
				</Button>
				<Button
					size="sm"
					variant="outline"
					class="text-destructive hover:text-destructive"
					onclick={() => (bulkDeleteConfirmOpen = true)}
					disabled={bulkActionPending}
				>
					Delete
				</Button>
				<Button size="sm" variant="ghost" onclick={() => (selectedFeedIds = [])} disabled={bulkActionPending}>
					Clear Selection
				</Button>
			</Card.Content>
		</Card.Root>
	{/if}

	<!-- Feed List -->
	<Card.Root>
		<Card.Content class="p-0">
			{#if feedsQuery.isPending}
				<div class="p-4 space-y-3">
					{#each [1, 2, 3, 4, 5] as _}
						<div class="flex items-center gap-4">
							<Skeleton class="h-10 w-10 rounded" />
							<div class="flex-1 space-y-2">
								<Skeleton class="h-4 w-48" />
								<Skeleton class="h-3 w-64" />
							</div>
							<Skeleton class="h-6 w-16" />
						</div>
					{/each}
				</div>
			{:else if !filteredFeeds.length}
				<div class="flex flex-col items-center justify-center py-12 text-center">
					<Rss class="h-12 w-12 text-muted-foreground/50" />
					<p class="mt-4 text-lg font-medium">
						{searchQuery ? 'No feeds match your search' : 'No feeds yet'}
					</p>
					<p class="text-sm text-muted-foreground">
						{searchQuery ? 'Try a different search term' : 'Add your first RSS feed to get started'}
					</p>
					{#if !searchQuery}
						<Button onclick={openAddDialog} class="mt-4">
							<Plus class="mr-2 h-4 w-4" />
							Add Feed
						</Button>
					{/if}
				</div>
			{:else}
					<!-- Desktop Table -->
					<div class="hidden md:block">
						<Table.Root>
							<Table.Header>
								<Table.Row>
									<Table.Head class="w-[44px]">
										<input
											type="checkbox"
											aria-label="Select all visible feeds"
											checked={allFilteredSelected}
											onchange={(e) =>
												toggleSelectAllFiltered((e.target as HTMLInputElement).checked)}
										/>
									</Table.Head>
									<Table.Head>Feed</Table.Head>
									<Table.Head>Mode</Table.Head>
									<Table.Head>Max Articles</Table.Head>
									<Table.Head>Status</Table.Head>
								<Table.Head class="w-[100px]">Actions</Table.Head>
							</Table.Row>
						</Table.Header>
							<Table.Body>
								{#each filteredFeeds as feed}
									<Table.Row>
										<Table.Cell>
											<input
												type="checkbox"
												aria-label={`Select ${feed.title}`}
												checked={selectedFeedIds.includes(feed.id)}
												onchange={(e) =>
													toggleFeedSelection(feed.id, (e.target as HTMLInputElement).checked)}
											/>
										</Table.Cell>
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
									<Table.Cell>{feed.max_articles}</Table.Cell>
									<Table.Cell>
										<button
											type="button"
											class="inline-flex items-center gap-2"
											title={feed.is_active ? 'Pause feed' : 'Activate feed'}
											aria-pressed={feed.is_active}
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
												<DropdownMenu.Item onclick={() => handleClearSeen(feed)}>
													<RotateCcw class="mr-2 h-4 w-4" />
													Clear Seen Articles
												</DropdownMenu.Item>
												<DropdownMenu.Separator />
												<DropdownMenu.Item
													class="text-destructive"
													onclick={() => handleDeleteFeed(feed)}
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
										<div class="mb-1 flex items-center gap-2">
											<input
												type="checkbox"
												aria-label={`Select ${feed.title}`}
												checked={selectedFeedIds.includes(feed.id)}
												onchange={(e) =>
													toggleFeedSelection(feed.id, (e.target as HTMLInputElement).checked)}
											/>
											<p class="font-medium truncate">{feed.title}</p>
										</div>
										<a
											href={feed.url}
											target="_blank"
										rel="noopener noreferrer"
										class="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
									>
										<span class="truncate">{feed.url}</span>
										<ExternalLink class="h-3 w-3 flex-shrink-0" />
									</a>
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
										<DropdownMenu.Item onclick={() => handleClearSeen(feed)}>
											<RotateCcw class="mr-2 h-4 w-4" />
											Clear Seen Articles
										</DropdownMenu.Item>
										<DropdownMenu.Separator />
										<DropdownMenu.Item
											class="text-destructive"
											onclick={() => handleDeleteFeed(feed)}
										>
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
									title={feed.is_active ? 'Pause feed' : 'Activate feed'}
									aria-pressed={feed.is_active}
									disabled={toggleFeedMutation.isPending && updatingFeedId === feed.id}
									onclick={() => handleToggleFeed(feed)}
								>
									<Badge variant={feed.is_active ? 'default' : 'outline'} class="text-xs">
										{feed.is_active ? 'Active' : 'Paused'}
									</Badge>
									{#if toggleFeedMutation.isPending && updatingFeedId === feed.id}
										<Loader2 class="h-3.5 w-3.5 animate-spin text-muted-foreground" />
									{/if}
								</button>
								<span class="text-xs text-muted-foreground">Max {feed.max_articles} articles</span>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</Card.Content>
	</Card.Root>
</div>

<!-- Add Feed Dialog -->
<Dialog.Root bind:open={addDialogOpen}>
	<Dialog.Content class="sm:max-w-md">
		<Dialog.Header>
			<Dialog.Title>Add Feed</Dialog.Title>
			<Dialog.Description>Add a new RSS or Atom feed to your digest</Dialog.Description>
		</Dialog.Header>
		<form onsubmit={handleAddFeed} class="space-y-4">
			<div class="space-y-2">
				<Label for="url">Feed URL</Label>
				<Input
					id="url"
					type="url"
					placeholder="https://example.com/feed.xml"
					bind:value={formUrl}
					required
				/>
			</div>
			<div class="space-y-2">
				<Label for="title">Title (optional)</Label>
				<Input id="title" placeholder="Feed title" bind:value={formTitle} />
			</div>
			<div class="grid grid-cols-2 gap-4">
				<div class="space-y-2">
					<Label>Mode</Label>
					<Select.Root type="single" name="mode" value={formMode} onValueChange={(v) => (formMode = v as 'raw' | 'summarize')}>
						<Select.Trigger>
							<span class="capitalize">{formMode}</span>
						</Select.Trigger>
						<Select.Content>
							<Select.Item value="raw">Raw</Select.Item>
							<Select.Item value="summarize">Summarize</Select.Item>
						</Select.Content>
					</Select.Root>
				</div>
				<div class="space-y-2">
					<Label for="maxArticles">Max Articles</Label>
					<Input
						id="maxArticles"
						type="number"
						min={0}
						max={50}
						bind:value={formMaxArticles}
					/>
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
						Add Feed
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
			<AlertDialog.Title>Delete Feed</AlertDialog.Title>
			<AlertDialog.Description>
				Are you sure you want to delete "{feedToDelete?.title}"? This action cannot be undone.
			</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Cancel</AlertDialog.Cancel>
			<AlertDialog.Action onclick={confirmDelete} class="bg-destructive text-destructive-foreground hover:bg-destructive/90">
				{#if deleteFeedMutation.isPending}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
				{/if}
				Delete
			</AlertDialog.Action>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>

<!-- Bulk Delete Confirmation -->
<AlertDialog.Root bind:open={bulkDeleteConfirmOpen}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Delete Selected Feeds</AlertDialog.Title>
			<AlertDialog.Description>
				This will permanently delete {selectedFeedsCount} selected feed{selectedFeedsCount === 1
					? ''
					: 's'}.
			</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel disabled={bulkActionPending}>Cancel</AlertDialog.Cancel>
			<AlertDialog.Action
				class="bg-destructive text-destructive-foreground hover:bg-destructive/90"
				onclick={confirmBulkDelete}
				disabled={bulkActionPending}
			>
				{#if bulkActionPending}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
				{/if}
				Delete Selected
			</AlertDialog.Action>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>

<!-- Clear Seen Articles Confirmation -->
<AlertDialog.Root open={!!feedToClearSeen} onOpenChange={(open) => !open && (feedToClearSeen = null)}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Clear Seen Articles</AlertDialog.Title>
			<AlertDialog.Description>
				This will reset the "seen" history for "{feedToClearSeen?.title}". Previously processed articles will appear in future digests again.
			</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Cancel</AlertDialog.Cancel>
			<AlertDialog.Action onclick={confirmClearSeen}>
				{#if clearSeenMutation.isPending}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
				{/if}
				Clear History
			</AlertDialog.Action>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>

<!-- Edit Feed Dialog -->
<Dialog.Root bind:open={editDialogOpen} onOpenChange={(open) => !open && (feedToEdit = null)}>
	<Dialog.Content class="sm:max-w-md">
		<Dialog.Header>
			<Dialog.Title>Edit Feed</Dialog.Title>
			<Dialog.Description>Update feed settings</Dialog.Description>
		</Dialog.Header>
		<form onsubmit={handleUpdateFeed} class="space-y-4">
			<div class="space-y-2">
				<Label for="edit-url">Feed URL</Label>
				<Input
					id="edit-url"
					type="url"
					value={feedToEdit?.url ?? ''}
					disabled
					class="bg-muted"
				/>
				<p class="text-xs text-muted-foreground">URL cannot be changed</p>
			</div>
			<div class="space-y-2">
				<Label for="edit-title">Title</Label>
				<Input id="edit-title" placeholder="Feed title" bind:value={editTitle} required />
			</div>
			<div class="grid grid-cols-2 gap-4">
				<div class="space-y-2">
					<Label>Mode</Label>
					<Select.Root type="single" name="edit-mode" value={editMode} onValueChange={(v) => (editMode = v as 'raw' | 'summarize')}>
						<Select.Trigger>
							<span class="capitalize">{editMode}</span>
						</Select.Trigger>
						<Select.Content>
							<Select.Item value="raw">Raw</Select.Item>
							<Select.Item value="summarize">Summarize</Select.Item>
						</Select.Content>
					</Select.Root>
				</div>
				<div class="space-y-2">
					<Label for="edit-maxArticles">Max Articles</Label>
					<Input
						id="edit-maxArticles"
						type="number"
						min={0}
						max={50}
						bind:value={editMaxArticles}
					/>
				</div>
			</div>
			<div class="flex items-center justify-between rounded-lg border p-3">
				<div class="space-y-0.5">
					<Label for="edit-active">Active</Label>
					<p class="text-xs text-muted-foreground">Include this feed in digests</p>
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
