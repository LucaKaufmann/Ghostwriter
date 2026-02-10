<script lang="ts">
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { createQuery } from '@tanstack/svelte-query';
	import { api, type DigestArticle } from '$lib/api';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import * as ScrollArea from '$lib/components/ui/scroll-area';
	import { Separator } from '$lib/components/ui/separator';
	import * as Sheet from '$lib/components/ui/sheet';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { toast } from 'svelte-sonner';
	import {
		ArrowLeft,
		ChevronLeft,
		ChevronRight,
		ExternalLink,
		List,
		Loader2,
		RefreshCw
	} from 'lucide-svelte';

	const digestId = $derived($page.params.id ?? '');

	let mobileTocOpen = $state(false);
	let selectedArticleId = $state<string | null>(null);

	const articlesQuery = createQuery(() => ({
		queryKey: ['digest-articles', digestId],
		queryFn: () => api.getDigestArticles(digestId),
		enabled: digestId.length > 0
	}));

	const sortedArticles = $derived.by(() => {
		const articles = articlesQuery.data?.articles ?? [];
		return [...articles].sort((a, b) => a.sort_order - b.sort_order);
	});

	$effect(() => {
		if (selectedArticleId) return;
		if (!sortedArticles.length) return;
		selectedArticleId = sortedArticles[0].id;
	});

	const selectedIndex = $derived.by(() =>
		selectedArticleId ? sortedArticles.findIndex((a) => a.id === selectedArticleId) : -1
	);
	const selectedArticle = $derived.by(() =>
		selectedIndex >= 0 ? sortedArticles[selectedIndex] : null
	);

	function selectArticle(id: string) {
		selectedArticleId = id;
		mobileTocOpen = false;
	}

	function selectPrev() {
		if (selectedIndex <= 0) return;
		selectedArticleId = sortedArticles[selectedIndex - 1].id;
	}

	function selectNext() {
		if (selectedIndex < 0) return;
		if (selectedIndex >= sortedArticles.length - 1) return;
		selectedArticleId = sortedArticles[selectedIndex + 1].id;
	}

	const isMediaContent = $derived(
		selectedArticle?.content_type === 'podcast' || selectedArticle?.content_type === 'youtube'
	);

	const sourceQuery = createQuery(() => ({
		queryKey: ['digest-article-source', digestId, selectedArticleId],
		queryFn: () => api.getDigestArticleSource(digestId, selectedArticleId!),
		enabled: browser && digestId.length > 0 && !!selectedArticleId && !isMediaContent,
		retry: 0
	}));

	function escapeHtml(value: string): string {
		return value
			.replaceAll('&', '&amp;')
			.replaceAll('<', '&lt;')
			.replaceAll('>', '&gt;')
			.replaceAll('"', '&quot;')
			.replaceAll("'", '&#39;');
	}

	function looksLikeHtml(value: string): boolean {
		return /<[a-z][\\s\\S]*>/i.test(value);
	}

	function plainTextToHtml(value: string): string {
		const text = value.trim();
		if (!text) return '';
		const paragraphs = text.split(/\\n\\s*\\n/g);
		return paragraphs
			.map((p) => `<p>${escapeHtml(p).replaceAll('\\n', '<br />')}</p>`)
			.join('\\n');
	}

	let sanitizerPromise: Promise<any> | null = null;
	async function getSanitizer(): Promise<any> {
		if (!browser) return null;
		if (!sanitizerPromise) {
			sanitizerPromise = import('dompurify').then((m) => m.default);
		}
		return sanitizerPromise;
	}

	async function sanitizeAndNormalize(
		rawHtml: string,
		baseUrl?: string
	): Promise<string> {
		const DOMPurify = await getSanitizer();
		if (!DOMPurify) return '';

		const fragment = DOMPurify.sanitize(rawHtml, {
			USE_PROFILES: { html: true },
			RETURN_DOM_FRAGMENT: true,
			FORBID_ATTR: ['style', 'class', 'id']
		}) as DocumentFragment;

		const container = document.createElement('div');
		container.appendChild(fragment);

		// Normalize outgoing links + resolve relative URLs.
		const base = baseUrl;
		for (const anchor of Array.from(container.querySelectorAll('a[href]'))) {
			const href = anchor.getAttribute('href');
			if (!href) continue;
			if (base) {
				try {
					anchor.setAttribute('href', new URL(href, base).toString());
				} catch {
					// Leave as-is; user can still try clicking it.
				}
			}
			anchor.setAttribute('target', '_blank');
			anchor.setAttribute('rel', 'noopener noreferrer');
		}

		for (const img of Array.from(container.querySelectorAll('img[src]'))) {
			const src = img.getAttribute('src');
			if (!src) continue;
			if (base) {
				try {
					img.setAttribute('src', new URL(src, base).toString());
				} catch {
					// noop
				}
			}
			img.setAttribute('loading', 'lazy');
			img.setAttribute('decoding', 'async');
		}

		return container.innerHTML;
	}

	type ReaderArticle = {
		title: string;
		byline: string | null;
		contentHtml: string;
	};

	let reader = $state<ReaderArticle | null>(null);
	let readerError = $state<string | null>(null);
	let fallbackHtml = $state<string>('');
	let renderSeq = 0;

	$effect(() => {
		if (!browser) return;
		const article = selectedArticle;
		renderSeq += 1;
		const seq = renderSeq;

		reader = null;
		readerError = null;
		fallbackHtml = '';

		if (!article) return;

		// Always compute fallback from stored digest content.
		void (async () => {
			const raw = looksLikeHtml(article.content) ? article.content : plainTextToHtml(article.content);
			const sanitized = await sanitizeAndNormalize(raw, article.url);
			if (seq !== renderSeq) return;
			fallbackHtml = sanitized;
		})().catch(() => {
			// If fallback fails, just leave it empty; the page will still link to original.
		});

		const source = sourceQuery.data;
		if (!source) return;

		void (async () => {
			const { Readability } = await import('@mozilla/readability');
			const doc = new DOMParser().parseFromString(source.html, 'text/html');
			const parsed = new Readability(doc).parse();
			if (!parsed?.content) {
				throw new Error('Reader extraction failed');
			}
			const contentHtml = await sanitizeAndNormalize(
				parsed.content,
				source.final_url || source.url
			);
			if (seq !== renderSeq) return;
			reader = {
				title: parsed.title?.trim() || article.title,
				byline: parsed.byline?.trim() || null,
				contentHtml
			};
		})().catch((err) => {
			if (seq !== renderSeq) return;
			readerError = err instanceof Error ? err.message : 'Reader extraction failed';
		});
	});

	function getModeVariant(mode: string): 'default' | 'secondary' {
		return mode === 'summarize' ? 'default' : 'secondary';
	}

	function tocItemClasses(article: DigestArticle): string {
		const isSelected = article.id === selectedArticleId;
		return [
			'w-full text-left rounded-md px-3 py-2 transition-colors',
			isSelected ? 'bg-accent' : 'hover:bg-accent/60'
		].join(' ');
	}

	function handleReaderRetry() {
		if (!selectedArticle) return;
		sourceQuery.refetch().catch((err) => {
			toast.error('Failed to reload article', {
				description: err instanceof Error ? err.message : 'Unknown error'
			});
		});
	}
</script>

<svelte:head>
	<title>Reader - Ghostwriter</title>
</svelte:head>

<div class="space-y-4">
	<div class="flex items-start justify-between gap-3">
		<div class="flex items-start gap-2 min-w-0">
			<Button variant="ghost" size="icon" onclick={() => goto('/digests')}>
				<ArrowLeft class="h-4 w-4" />
				<span class="sr-only">Back to digests</span>
			</Button>
			<div class="min-w-0">
				<h1 class="text-xl font-bold tracking-tight">Reader</h1>
				<p class="text-sm text-muted-foreground">
					{#if articlesQuery.isPending}
						Loading articles...
					{:else if articlesQuery.isError}
						Failed to load digest articles
					{:else}
						{sortedArticles.length} articles
					{/if}
				</p>
			</div>
		</div>

		<div class="flex items-center gap-2">
			{#if selectedArticle}
				<a href={selectedArticle.url} target="_blank" rel="noopener noreferrer">
					<Button variant="outline" size="sm">
						<ExternalLink class="mr-2 h-4 w-4" />
						Original
					</Button>
				</a>
			{/if}

			<!-- Mobile TOC -->
			<div class="lg:hidden">
				<Sheet.Root bind:open={mobileTocOpen}>
					<Sheet.Trigger>
						{#snippet child({ props })}
							<Button {...props} variant="outline" size="sm">
								<List class="mr-2 h-4 w-4" />
								Contents
							</Button>
						{/snippet}
					</Sheet.Trigger>
					<Sheet.Content side="left" class="w-[90vw] sm:w-96 p-0">
						<div class="border-b p-4">
							<p class="text-sm font-semibold">Articles</p>
							<p class="text-xs text-muted-foreground">{sortedArticles.length} total</p>
						</div>
						<ScrollArea.Root class="h-[calc(100vh-6rem)]">
							<div class="p-2 space-y-1">
								{#each sortedArticles as article}
									<button
										type="button"
										class={tocItemClasses(article)}
										onclick={() => selectArticle(article.id)}
									>
										<p class="text-sm font-medium line-clamp-2">{article.title}</p>
										<p class="text-xs text-muted-foreground truncate">{article.feed_title}</p>
									</button>
								{/each}
							</div>
						</ScrollArea.Root>
					</Sheet.Content>
				</Sheet.Root>
			</div>
		</div>
	</div>

	<Separator />

	<div class="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)] items-start">
		<!-- Desktop TOC -->
		<div class="hidden lg:block">
			<Card.Root class="sticky top-6">
				<Card.Header class="pb-3">
					<Card.Title class="text-base">Articles</Card.Title>
					<Card.Description>{sortedArticles.length} total</Card.Description>
				</Card.Header>
				<Card.Content class="p-0">
					<ScrollArea.Root class="h-[calc(100vh-14rem)]">
						<div class="p-2 space-y-1">
							{#each sortedArticles as article}
								<button
									type="button"
									class={tocItemClasses(article)}
									onclick={() => selectArticle(article.id)}
								>
									<p class="text-sm font-medium line-clamp-2">{article.title}</p>
									<p class="text-xs text-muted-foreground truncate">{article.feed_title}</p>
								</button>
							{/each}
						</div>
					</ScrollArea.Root>
				</Card.Content>
			</Card.Root>
		</div>

		<!-- Reader -->
		<div class="min-w-0 space-y-4">
			{#if articlesQuery.isPending}
				<div class="space-y-3">
					<Skeleton class="h-8 w-2/3" />
					<Skeleton class="h-4 w-1/2" />
					<Skeleton class="h-64 w-full" />
				</div>
			{:else if articlesQuery.isError}
				<Card.Root>
					<Card.Content class="py-8 text-center">
						<p class="font-medium">Could not load digest articles</p>
						<p class="mt-1 text-sm text-muted-foreground">
							{articlesQuery.error instanceof Error ? articlesQuery.error.message : 'Unknown error'}
						</p>
						<Button class="mt-4" variant="outline" onclick={() => articlesQuery.refetch()}>
							<RefreshCw class="mr-2 h-4 w-4" />
							Retry
						</Button>
					</Card.Content>
				</Card.Root>
			{:else if !selectedArticle}
				<Card.Root>
					<Card.Content class="py-10 text-center text-muted-foreground">
						No articles in this digest
					</Card.Content>
				</Card.Root>
			{:else}
				<div class="flex items-start justify-between gap-3">
					<div class="min-w-0">
						<h2 class="text-2xl font-bold leading-tight">
							{reader?.title ?? selectedArticle.title}
						</h2>
						<div class="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
							<span class="font-medium text-foreground/80">{selectedArticle.feed_title}</span>
							<Badge variant={getModeVariant(selectedArticle.mode)} class="text-xs">
								{selectedArticle.mode}
							</Badge>
							<span>{selectedArticle.word_count} words</span>
							{#if selectedArticle.ai_failed}
								<Badge variant="destructive" class="text-xs">AI failed</Badge>
							{/if}
							{#if reader?.byline}
								<span>By {reader.byline}</span>
							{/if}
						</div>
					</div>

					<div class="flex items-center gap-1 flex-shrink-0">
						<Button variant="ghost" size="icon" disabled={selectedIndex <= 0} onclick={selectPrev}>
							<ChevronLeft class="h-4 w-4" />
							<span class="sr-only">Previous article</span>
						</Button>
						<Button
							variant="ghost"
							size="icon"
							disabled={selectedIndex >= sortedArticles.length - 1}
							onclick={selectNext}
						>
							<ChevronRight class="h-4 w-4" />
							<span class="sr-only">Next article</span>
						</Button>
					</div>
				</div>

				<Card.Root>
					<Card.Content class="p-6">
						{#if isMediaContent}
							{#if fallbackHtml}
								<div>
									<p class="mb-2 text-xs font-semibold tracking-wide uppercase text-muted-foreground">
										{selectedArticle?.content_type === 'podcast' ? 'Transcript' : 'Transcript'}
									</p>
									<article class="prose prose-slate max-w-none">
										{@html fallbackHtml}
									</article>
								</div>
							{:else}
								<div class="space-y-3">
									<div class="flex items-center gap-2 text-sm text-muted-foreground">
										<Loader2 class="h-4 w-4 animate-spin" />
										Loading transcript...
									</div>
									<Skeleton class="h-5 w-3/4" />
									<Skeleton class="h-40 w-full" />
								</div>
							{/if}
						{:else if sourceQuery.isPending}
							<div class="space-y-3">
								<div class="flex items-center gap-2 text-sm text-muted-foreground">
									<Loader2 class="h-4 w-4 animate-spin" />
									Loading reader mode...
								</div>
								<Skeleton class="h-5 w-3/4" />
								<Skeleton class="h-5 w-2/3" />
								<Skeleton class="h-40 w-full" />
							</div>
						{:else if reader && !readerError}
							<article class="prose prose-slate max-w-none prose-headings:scroll-mt-24 prose-a:break-words">
								{@html reader.contentHtml}
							</article>
						{:else}
							<div class="space-y-4">
								<div class="rounded-md border bg-muted/30 p-3">
									<p class="text-sm font-medium">Reader mode unavailable</p>
									<p class="text-xs text-muted-foreground">
										{#if sourceQuery.isError}
											{sourceQuery.error instanceof Error
												? sourceQuery.error.message
												: 'Upstream fetch failed'}
										{:else if readerError}
											{readerError}
										{:else}
											Upstream fetch failed
										{/if}
									</p>
									<Button class="mt-3" variant="outline" size="sm" onclick={handleReaderRetry}>
										<RefreshCw class="mr-2 h-4 w-4" />
										Retry reader mode
									</Button>
								</div>

								{#if fallbackHtml}
									<div>
										<p class="mb-2 text-xs font-semibold tracking-wide uppercase text-muted-foreground">
											Digest content
										</p>
										<article class="prose prose-slate max-w-none">
											{@html fallbackHtml}
										</article>
									</div>
								{:else}
									<p class="text-sm text-muted-foreground">
										No stored digest content available for this article.
									</p>
								{/if}
							</div>
						{/if}
					</Card.Content>
				</Card.Root>
			{/if}
		</div>
	</div>
</div>
