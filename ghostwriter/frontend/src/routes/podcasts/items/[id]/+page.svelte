<script lang="ts">
	import { page } from '$app/stores';
	import { createQuery } from '@tanstack/svelte-query';
	import { api } from '$lib/api/client';
	import * as Card from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { ArrowLeft, ExternalLink, Headphones } from 'lucide-svelte';

	const itemId = $derived($page.params.id);

	const itemQuery = createQuery(() => ({
		queryKey: ['media-item', itemId],
		queryFn: () => api.getMediaItem(itemId!),
		enabled: !!itemId
	}));

	function parseUTC(dateStr: string): Date {
		if (!dateStr.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(dateStr)) {
			return new Date(dateStr + 'Z');
		}
		return new Date(dateStr);
	}

	function formatDate(dateStr: string): string {
		return parseUTC(dateStr).toLocaleDateString('en-US', {
			month: 'long',
			day: 'numeric',
			year: 'numeric'
		});
	}
</script>

<svelte:head>
	<title>{itemQuery.data?.title ?? 'Transcript'} - Ghostwriter</title>
</svelte:head>

<div class="space-y-6 min-w-0">
	<div class="flex items-center gap-4">
		<Button variant="ghost" size="icon" href="/podcasts">
			<ArrowLeft class="h-4 w-4" />
		</Button>
		<div>
			<h1 class="text-2xl font-bold tracking-tight">Transcript</h1>
			<p class="text-muted-foreground">Podcast episode transcript</p>
		</div>
	</div>

	{#if itemQuery.isPending}
		<Card.Root>
			<Card.Content class="pt-6 space-y-4">
				<Skeleton class="h-6 w-3/4" />
				<Skeleton class="h-4 w-1/2" />
				<div class="space-y-2 mt-6">
					{#each [1, 2, 3, 4, 5] as _}
						<Skeleton class="h-4 w-full" />
					{/each}
				</div>
			</Card.Content>
		</Card.Root>
	{:else if itemQuery.error}
		<Card.Root>
			<Card.Content class="pt-6">
				<div class="flex flex-col items-center justify-center py-12 text-center">
					<Headphones class="h-12 w-12 text-muted-foreground/50" />
					<p class="mt-4 text-lg font-medium">Transcript not found</p>
					<Button variant="outline" class="mt-4" href="/podcasts">
						Back to Podcasts
					</Button>
				</div>
			</Card.Content>
		</Card.Root>
	{:else if itemQuery.data}
		{@const item = itemQuery.data}
		<Card.Root>
			<Card.Header>
				<div class="space-y-2">
					<Card.Title class="text-xl">{item.title}</Card.Title>
					<div class="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
						{#if item.author}
							<span>{item.author}</span>
							<span>-</span>
						{/if}
						<span>{item.word_count.toLocaleString()} words</span>
						{#if item.completed_at}
							<span>-</span>
							<span>{formatDate(item.completed_at)}</span>
						{/if}
					</div>
					<div class="flex flex-wrap gap-2">
						<Badge variant={item.is_summary ? 'default' : 'secondary'}>
							{item.is_summary ? 'AI Summary' : 'Full Transcript'}
						</Badge>
						{#if item.ai_failed}
							<Badge variant="outline">AI Fallback</Badge>
						{/if}
						{#if item.consumed_at}
							<Badge variant="outline">Included in digest</Badge>
						{/if}
					</div>
				</div>
			</Card.Header>
			<Card.Content>
				<div class="prose prose-sm max-w-none dark:prose-invert">
					{#each item.content.split('\n\n') as paragraph}
						{#if paragraph.trim()}
							<p>{paragraph.trim()}</p>
						{/if}
					{/each}
				</div>
				<div class="mt-6 pt-4 border-t">
					<a
						href={item.url}
						target="_blank"
						rel="noopener noreferrer"
						class="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
					>
						View original
						<ExternalLink class="h-3 w-3" />
					</a>
				</div>
			</Card.Content>
		</Card.Root>
	{/if}
</div>
