<script lang="ts">
	import { goto } from '$app/navigation';
	import { createQuery, createMutation, useQueryClient } from '@tanstack/svelte-query';
	import { api, type Digest } from '$lib/api';
	import * as Card from '$lib/components/ui/card';
	import * as Table from '$lib/components/ui/table';
	import * as AlertDialog from '$lib/components/ui/alert-dialog';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { Progress } from '$lib/components/ui/progress';
	import { formatUTCDate, parseUTC } from '$lib/utils/date';
	import { downloadDigestFile, getDigestStatusBadgeVariant } from '$lib/utils/digest';
	import { toast } from 'svelte-sonner';
	import {
		Play,
		Download,
		Trash2,
		Eye,
		BookCopy,
		Calendar,
		Loader2,
		MoreHorizontal,
		RefreshCw
	} from 'lucide-svelte';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';

	const queryClient = useQueryClient();

	// Queries
	const digestsQuery = createQuery(() => ({
		queryKey: ['digests', { limit: 20 }],
		queryFn: () => api.getDigests({ limit: 20 }),
		refetchInterval: (query) => {
			// Refetch more frequently if there's a processing digest
			const hasProcessing = query.state.data?.some((d) => d.status === 'processing');
			return hasProcessing ? 5000 : 30000;
		}
	}));

	// Mutations
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

	// State
	let digestToDelete = $state<Digest | null>(null);

	// Computed
	const processingDigest = $derived(digestsQuery.data?.find((d) => d.status === 'processing'));

	function openReader(digest: Digest) {
		goto(`/digests/${digest.id}/read`);
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

	function getDuration(digest: Digest): string | null {
		if (!digest.completed_at) return null;
		const start = parseUTC(digest.created_at).getTime();
		const end = parseUTC(digest.completed_at).getTime();
		const seconds = Math.round((end - start) / 1000);
		if (seconds < 60) return `${seconds}s`;
		const minutes = Math.floor(seconds / 60);
		const remainingSeconds = seconds % 60;
		return `${minutes}m ${remainingSeconds}s`;
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
	<title>Digests - Ghostwriter</title>
</svelte:head>

<div class="space-y-6">
	<div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
		<div>
			<h1 class="text-2xl font-bold tracking-tight">Digests</h1>
			<p class="text-muted-foreground">View and manage your generated digests</p>
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

	<!-- Processing Status -->
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

	<!-- Digests List -->
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
							<Skeleton class="h-6 w-20" />
						</div>
					{/each}
				</div>
			{:else if !digestsQuery.data?.length}
				<div class="flex flex-col items-center justify-center py-12 text-center">
					<BookCopy class="h-12 w-12 text-muted-foreground/50" />
					<p class="mt-4 text-lg font-medium">No digests yet</p>
					<p class="text-sm text-muted-foreground">
						Generate your first digest to see it here
					</p>
					<Button onclick={() => triggerMutation.mutate()} class="mt-4" disabled={triggerMutation.isPending}>
						<Play class="mr-2 h-4 w-4" />
						Generate Digest
					</Button>
				</div>
			{:else}
				<!-- Desktop Table -->
				<div class="hidden md:block">
					<Table.Root>
						<Table.Header>
							<Table.Row>
								<Table.Head>Date</Table.Head>
								<Table.Head>Period</Table.Head>
								<Table.Head>Articles</Table.Head>
								<Table.Head>Status</Table.Head>
								<Table.Head>Duration</Table.Head>
								<Table.Head class="w-[100px]">Actions</Table.Head>
							</Table.Row>
						</Table.Header>
						<Table.Body>
							{#each digestsQuery.data as digest}
								<Table.Row>
									<Table.Cell>
										<div class="flex items-center gap-2">
											<Calendar class="h-4 w-4 text-muted-foreground" />
											{formatDate(digest.created_at)}
										</div>
									</Table.Cell>
									<Table.Cell class="capitalize">{digest.period}</Table.Cell>
									<Table.Cell>
										{#if digest.total_articles > 0}
											{digest.total_articles}
										{:else}
											<span class="text-muted-foreground">—</span>
										{/if}
									</Table.Cell>
									<Table.Cell>
											<Badge variant={getDigestStatusBadgeVariant(digest.status)}>
											{digest.status}
										</Badge>
									</Table.Cell>
									<Table.Cell>
										{#if getDuration(digest)}
											{getDuration(digest)}
										{:else}
											<span class="text-muted-foreground">—</span>
										{/if}
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
												{#if digest.status === 'completed'}
													{#if digest.filename}
														<DropdownMenu.Item>
															{#snippet child({ props })}
																<button
																	{...props}
																	type="button"
																	onclick={() => downloadDigest(digest.filename!)}
																>
																	<Download class="mr-2 h-4 w-4" />
																	Download EPUB
																</button>
															{/snippet}
														</DropdownMenu.Item>
													{/if}
													<DropdownMenu.Item onclick={() => openReader(digest)}>
														<Eye class="mr-2 h-4 w-4" />
														View Articles
													</DropdownMenu.Item>
													<DropdownMenu.Separator />
												{/if}
												{#if digest.filename}
													<DropdownMenu.Item
														class="text-destructive"
														onclick={() => (digestToDelete = digest)}
													>
														<Trash2 class="mr-2 h-4 w-4" />
														Delete
													</DropdownMenu.Item>
												{/if}
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
					{#each digestsQuery.data as digest}
						<div class="p-4 space-y-2">
							<div class="flex items-start justify-between gap-2">
								<div class="min-w-0 flex-1">
									<p class="font-medium capitalize">{digest.period} Digest</p>
									<p class="text-sm text-muted-foreground">
										{formatDate(digest.created_at)}
									</p>
								</div>
									<Badge variant={getDigestStatusBadgeVariant(digest.status)}>
									{digest.status}
								</Badge>
							</div>
							<div class="flex items-center justify-between">
								<span class="text-sm text-muted-foreground">
									{#if digest.total_articles > 0}
										{digest.total_articles} articles
									{:else}
										—
									{/if}
									{#if getDuration(digest)}
										• {getDuration(digest)}
									{/if}
								</span>
								<div class="flex items-center gap-1">
									{#if digest.status === 'completed' && digest.filename}
										<Button
											variant="ghost"
											size="icon"
											onclick={() => downloadDigest(digest.filename!)}
										>
											<Download class="h-4 w-4" />
										</Button>
										<Button variant="ghost" size="icon" onclick={() => openReader(digest)}>
											<Eye class="h-4 w-4" />
										</Button>
									{/if}
									{#if digest.filename}
										<Button
											variant="ghost"
											size="icon"
											onclick={() => (digestToDelete = digest)}
											class="text-destructive"
										>
											<Trash2 class="h-4 w-4" />
										</Button>
									{/if}
								</div>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</Card.Content>
	</Card.Root>
</div>

<!-- Delete Confirmation -->
<AlertDialog.Root open={!!digestToDelete} onOpenChange={(open) => !open && (digestToDelete = null)}>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Delete Digest</AlertDialog.Title>
			<AlertDialog.Description>
				Are you sure you want to delete the {digestToDelete?.period} digest from{' '}
				{digestToDelete ? formatShortDate(digestToDelete.created_at) : ''}? This will also
				remove the EPUB file.
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
