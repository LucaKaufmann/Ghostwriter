<script lang="ts">
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { createQuery } from '@tanstack/svelte-query';
	import { onDestroy, onMount } from 'svelte';
	import { api, type DigestArticle } from '$lib/api';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import { Label } from '$lib/components/ui/label';
	import * as ScrollArea from '$lib/components/ui/scroll-area';
	import { Separator } from '$lib/components/ui/separator';
	import * as Sheet from '$lib/components/ui/sheet';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import * as Select from '$lib/components/ui/select';
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

	type ReaderFontSize = 'sm' | 'base' | 'lg' | 'xl';
	type ReaderLineHeight = 'normal' | 'relaxed' | 'loose';
	type ReaderWidth = 'narrow' | 'comfortable' | 'wide';

	type ReaderPreferences = {
		fontSize: ReaderFontSize;
		lineHeight: ReaderLineHeight;
		width: ReaderWidth;
	};

	type ReaderArticle = {
		title: string;
		byline: string | null;
		contentHtml: string;
	};

	const READER_PREFS_KEY = 'ghostwriter.reader.preferences.v1';
	const defaultReaderPreferences: ReaderPreferences = {
		fontSize: 'base',
		lineHeight: 'relaxed',
		width: 'comfortable'
	};

	const digestId = $derived($page.params.id ?? '');

	let mobileTocOpen = $state(false);
	let selectedArticleId = $state<string | null>(null);
	let reader = $state<ReaderArticle | null>(null);
	let readerError = $state<string | null>(null);
	let fallbackHtml = $state('');
	let renderSeq = 0;
	let readerPreferences = $state<ReaderPreferences>(defaultReaderPreferences);

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
		selectedArticleId ? sortedArticles.findIndex((article) => article.id === selectedArticleId) : -1
	);
	const selectedArticle = $derived.by(() =>
		selectedIndex >= 0 ? sortedArticles[selectedIndex] : null
	);

	const isMediaContent = $derived(
		selectedArticle?.content_type === 'podcast' || selectedArticle?.content_type === 'youtube'
	);

	const sourceQuery = createQuery(() => ({
		queryKey: ['digest-article-source', digestId, selectedArticleId],
		queryFn: () => api.getDigestArticleSource(digestId, selectedArticleId!),
		enabled: browser && digestId.length > 0 && !!selectedArticleId && !isMediaContent,
		retry: 0
	}));

	const fontSizeClass = $derived.by(() => {
		switch (readerPreferences.fontSize) {
			case 'sm':
				return 'text-sm';
			case 'lg':
				return 'text-lg';
			case 'xl':
				return 'text-xl';
			default:
				return 'text-base';
		}
	});

	const lineHeightClass = $derived.by(() => {
		switch (readerPreferences.lineHeight) {
			case 'normal':
				return 'leading-normal';
			case 'loose':
				return 'leading-loose';
			default:
				return 'leading-relaxed';
		}
	});

	const contentWidthClass = $derived.by(() => {
		switch (readerPreferences.width) {
			case 'narrow':
				return 'max-w-3xl';
			case 'wide':
				return 'max-w-5xl';
			default:
				return 'max-w-4xl';
		}
	});

	function selectArticle(id: string) {
		selectedArticleId = id;
		mobileTocOpen = false;
	}

	function selectPrev() {
		if (selectedIndex <= 0) return;
		selectedArticleId = sortedArticles[selectedIndex - 1].id;
	}

	function selectNext() {
		if (selectedIndex < 0 || selectedIndex >= sortedArticles.length - 1) return;
		selectedArticleId = sortedArticles[selectedIndex + 1].id;
	}

	function looksLikeEditableTarget(event: KeyboardEvent): boolean {
		const target = event.target;
		if (!(target instanceof HTMLElement)) return false;
		if (target.isContentEditable) return true;
		const tag = target.tagName.toLowerCase();
		return tag === 'input' || tag === 'textarea' || tag === 'select';
	}

	function handleKeyboardNavigation(event: KeyboardEvent) {
		if (looksLikeEditableTarget(event)) return;
		if (!sortedArticles.length) return;

		if (event.key === 'ArrowLeft' || event.key.toLowerCase() === 'k') {
			event.preventDefault();
			selectPrev();
			return;
		}

		if (event.key === 'ArrowRight' || event.key.toLowerCase() === 'j') {
			event.preventDefault();
			selectNext();
			return;
		}

		if (event.key === 'Home') {
			event.preventDefault();
			selectArticle(sortedArticles[0].id);
			return;
		}

		if (event.key === 'End') {
			event.preventDefault();
			selectArticle(sortedArticles[sortedArticles.length - 1].id);
			return;
		}

		if (/^[1-9]$/.test(event.key)) {
			const index = Number(event.key) - 1;
			if (index < sortedArticles.length) {
				event.preventDefault();
				selectArticle(sortedArticles[index].id);
			}
		}
	}

	onMount(() => {
		if (!browser) return;
		window.addEventListener('keydown', handleKeyboardNavigation);
		const storedPreferences = localStorage.getItem(READER_PREFS_KEY);
		if (!storedPreferences) return;
		try {
			const parsed = JSON.parse(storedPreferences) as Partial<ReaderPreferences>;
			if (parsed.fontSize && ['sm', 'base', 'lg', 'xl'].includes(parsed.fontSize)) {
				readerPreferences.fontSize = parsed.fontSize as ReaderFontSize;
			}
			if (parsed.lineHeight && ['normal', 'relaxed', 'loose'].includes(parsed.lineHeight)) {
				readerPreferences.lineHeight = parsed.lineHeight as ReaderLineHeight;
			}
			if (parsed.width && ['narrow', 'comfortable', 'wide'].includes(parsed.width)) {
				readerPreferences.width = parsed.width as ReaderWidth;
			}
		} catch {
			// Ignore invalid persisted preferences.
		}
	});

	onDestroy(() => {
		if (!browser) return;
		window.removeEventListener('keydown', handleKeyboardNavigation);
	});

	$effect(() => {
		if (!browser) return;
		localStorage.setItem(READER_PREFS_KEY, JSON.stringify(readerPreferences));
	});

	function escapeHtml(value: string): string {
		return value
			.replaceAll('&', '&amp;')
			.replaceAll('<', '&lt;')
			.replaceAll('>', '&gt;')
			.replaceAll('"', '&quot;')
			.replaceAll("'", '&#39;');
	}

	function looksLikeHtml(value: string): boolean {
		return /<[a-z][\s\S]*>/i.test(value);
	}

	function plainTextToHtml(value: string): string {
		const text = value.trim();
		if (!text) return '';
		const paragraphs = text.split(/\n\s*\n/g);
		return paragraphs
			.map((paragraph) => `<p>${escapeHtml(paragraph).replaceAll('\n', '<br />')}</p>`)
			.join('\n');
	}

	let sanitizerPromise: Promise<any> | null = null;
	async function getSanitizer(): Promise<any> {
		if (!browser) return null;
		if (!sanitizerPromise) {
			sanitizerPromise = import('dompurify').then((module) => module.default);
		}
		return sanitizerPromise;
	}

	async function sanitizeAndNormalize(rawHtml: string, baseUrl?: string): Promise<string> {
		const DOMPurify = await getSanitizer();
		if (!DOMPurify) return '';

		const fragment = DOMPurify.sanitize(rawHtml, {
			USE_PROFILES: { html: true },
			RETURN_DOM_FRAGMENT: true,
			FORBID_ATTR: ['style', 'class', 'id']
		}) as DocumentFragment;

		const container = document.createElement('div');
		container.appendChild(fragment);

		for (const anchor of Array.from(container.querySelectorAll('a[href]'))) {
			const href = anchor.getAttribute('href');
			if (!href) continue;
			if (baseUrl) {
				try {
					anchor.setAttribute('href', new URL(href, baseUrl).toString());
				} catch {
					// Keep the original href.
				}
			}
			anchor.setAttribute('target', '_blank');
			anchor.setAttribute('rel', 'noopener noreferrer');
		}

		for (const img of Array.from(container.querySelectorAll('img[src]'))) {
			const src = img.getAttribute('src');
			if (!src) continue;
			if (baseUrl) {
				try {
					img.setAttribute('src', new URL(src, baseUrl).toString());
				} catch {
					// Keep the original src.
				}
			}
			img.setAttribute('loading', 'lazy');
			img.setAttribute('decoding', 'async');
		}

		return container.innerHTML;
	}

	$effect(() => {
		if (!browser) return;
		const article = selectedArticle;
		renderSeq += 1;
		const sequence = renderSeq;

		reader = null;
		readerError = null;
		fallbackHtml = '';

		if (!article) return;

		void (async () => {
			const raw = looksLikeHtml(article.content) ? article.content : plainTextToHtml(article.content);
			const sanitized = await sanitizeAndNormalize(raw, article.url);
			if (sequence !== renderSeq) return;
			fallbackHtml = sanitized;
		})().catch(() => {
			// Fallback HTML remains empty on sanitize failure.
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
			const contentHtml = await sanitizeAndNormalize(parsed.content, source.final_url || source.url);
			if (sequence !== renderSeq) return;
			reader = {
				title: parsed.title?.trim() || article.title,
				byline: parsed.byline?.trim() || null,
				contentHtml
			};
		})().catch((error) => {
			if (sequence !== renderSeq) return;
			readerError = error instanceof Error ? error.message : 'Reader extraction failed';
		});
	});

	function getModeVariant(mode: string): 'default' | 'secondary' {
		return mode === 'summarize' ? 'default' : 'secondary';
	}

	function tocItemClasses(article: DigestArticle): string {
		const isSelected = article.id === selectedArticleId;
		return [
			'w-full text-left rounded-md px-3 py-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
			isSelected ? 'bg-accent' : 'hover:bg-accent/60'
		].join(' ');
	}

	function handleReaderRetry() {
		if (!selectedArticle) return;
		sourceQuery.refetch().catch((error) => {
			toast.error('Failed to reload article', {
				description: error instanceof Error ? error.message : 'Unknown error'
			});
		});
	}
</script>

<svelte:head>
	<title>Reader - Ghostwriter</title>
</svelte:head>

<div class="space-y-4">
	<div class="flex items-start justify-between gap-3">
		<div class="min-w-0">
			<div class="flex items-start gap-2">
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
			<p class="ml-11 mt-1 text-xs text-muted-foreground">
				Keyboard: <kbd class="rounded border px-1">←</kbd>/<kbd class="rounded border px-1">→</kbd>
				or <kbd class="rounded border px-1">J</kbd>/<kbd class="rounded border px-1">K</kbd> for previous/next,
				<kbd class="rounded border px-1">1-9</kbd> to jump from contents.
			</p>
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
					<Sheet.Content side="left" class="w-[90vw] p-0 sm:w-96">
						<div class="border-b p-4">
							<p class="text-sm font-semibold">Articles</p>
							<p class="text-xs text-muted-foreground">{sortedArticles.length} total</p>
						</div>
						<ScrollArea.Root class="h-[calc(100vh-6rem)]">
							<div class="space-y-1 p-2">
								{#each sortedArticles as article}
									<button
										type="button"
										class={tocItemClasses(article)}
										aria-current={article.id === selectedArticleId ? 'true' : undefined}
										onclick={() => selectArticle(article.id)}
									>
										<p class="line-clamp-2 text-sm font-medium">{article.title}</p>
										<p class="truncate text-xs text-muted-foreground">{article.feed_title}</p>
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

	<div class="rounded-lg border bg-muted/20 p-3">
		<div class="grid gap-3 sm:grid-cols-3">
			<div class="space-y-1">
				<Label for="reader-font-size">Text size</Label>
				<Select.Root
					type="single"
					name="reader-font-size"
					value={readerPreferences.fontSize}
					onValueChange={(value) => (readerPreferences.fontSize = value as ReaderFontSize)}
				>
					<Select.Trigger id="reader-font-size">
						<span class="capitalize">{readerPreferences.fontSize}</span>
					</Select.Trigger>
					<Select.Content>
						<Select.Item value="sm">Small</Select.Item>
						<Select.Item value="base">Base</Select.Item>
						<Select.Item value="lg">Large</Select.Item>
						<Select.Item value="xl">Extra Large</Select.Item>
					</Select.Content>
				</Select.Root>
			</div>
			<div class="space-y-1">
				<Label for="reader-line-height">Line height</Label>
				<Select.Root
					type="single"
					name="reader-line-height"
					value={readerPreferences.lineHeight}
					onValueChange={(value) => (readerPreferences.lineHeight = value as ReaderLineHeight)}
				>
					<Select.Trigger id="reader-line-height">
						<span class="capitalize">{readerPreferences.lineHeight}</span>
					</Select.Trigger>
					<Select.Content>
						<Select.Item value="normal">Normal</Select.Item>
						<Select.Item value="relaxed">Relaxed</Select.Item>
						<Select.Item value="loose">Loose</Select.Item>
					</Select.Content>
				</Select.Root>
			</div>
			<div class="space-y-1">
				<Label for="reader-width">Reading width</Label>
				<Select.Root
					type="single"
					name="reader-width"
					value={readerPreferences.width}
					onValueChange={(value) => (readerPreferences.width = value as ReaderWidth)}
				>
					<Select.Trigger id="reader-width">
						<span class="capitalize">{readerPreferences.width}</span>
					</Select.Trigger>
					<Select.Content>
						<Select.Item value="narrow">Narrow</Select.Item>
						<Select.Item value="comfortable">Comfortable</Select.Item>
						<Select.Item value="wide">Wide</Select.Item>
					</Select.Content>
				</Select.Root>
			</div>
		</div>
	</div>

	<div class="grid items-start gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
		<div class="hidden lg:block">
			<Card.Root class="sticky top-6">
				<Card.Header class="pb-3">
					<Card.Title class="text-base">Articles</Card.Title>
					<Card.Description>{sortedArticles.length} total</Card.Description>
				</Card.Header>
				<Card.Content class="p-0">
					<ScrollArea.Root class="h-[calc(100vh-14rem)]">
						<div class="space-y-1 p-2">
							{#each sortedArticles as article}
								<button
									type="button"
									class={tocItemClasses(article)}
									aria-current={article.id === selectedArticleId ? 'true' : undefined}
									onclick={() => selectArticle(article.id)}
								>
									<p class="line-clamp-2 text-sm font-medium">{article.title}</p>
									<p class="truncate text-xs text-muted-foreground">{article.feed_title}</p>
								</button>
							{/each}
						</div>
					</ScrollArea.Root>
				</Card.Content>
			</Card.Root>
		</div>

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
						<h2 class="text-2xl font-bold leading-tight">{reader?.title ?? selectedArticle.title}</h2>
						<div class="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
							<span class="font-medium text-foreground/80">{selectedArticle.feed_title}</span>
							<Badge variant={getModeVariant(selectedArticle.mode)} class="text-xs">{selectedArticle.mode}</Badge>
							<span>{selectedArticle.word_count} words</span>
							{#if selectedArticle.ai_failed}
								<Badge variant="destructive" class="text-xs">AI failed</Badge>
							{/if}
							{#if reader?.byline}
								<span>By {reader.byline}</span>
							{/if}
						</div>
					</div>

					<div class="flex flex-shrink-0 items-center gap-1">
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
						<div class={`mx-auto w-full ${contentWidthClass}`}>
							{#if isMediaContent}
								{#if fallbackHtml}
									<div>
										<p class="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Transcript</p>
										<article
											class={`reader-prose prose prose-slate dark:prose-invert max-w-none prose-headings:scroll-mt-24 prose-a:break-words ${fontSizeClass} ${lineHeightClass}`}
										>
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
								<article
									class={`reader-prose prose prose-slate dark:prose-invert max-w-none prose-headings:scroll-mt-24 prose-a:break-words ${fontSizeClass} ${lineHeightClass}`}
								>
									{@html reader.contentHtml}
								</article>
							{:else}
								<div class="space-y-4">
									<div class="rounded-md border bg-muted/30 p-3">
										<p class="text-sm font-medium">Reader mode unavailable</p>
										<p class="text-xs text-muted-foreground">
											{#if sourceQuery.isError}
												{sourceQuery.error instanceof Error ? sourceQuery.error.message : 'Upstream fetch failed'}
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
											<p class="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
												Digest content
											</p>
											<article
												class={`reader-prose prose prose-slate dark:prose-invert max-w-none prose-headings:scroll-mt-24 prose-a:break-words ${fontSizeClass} ${lineHeightClass}`}
											>
												{@html fallbackHtml}
											</article>
										</div>
									{:else}
										<p class="text-sm text-muted-foreground">No stored digest content available for this article.</p>
									{/if}
								</div>
							{/if}
						</div>
					</Card.Content>
				</Card.Root>
			{/if}
		</div>
	</div>
</div>
