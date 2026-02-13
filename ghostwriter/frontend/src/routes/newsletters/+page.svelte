<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { api } from '$lib/api';
	import * as Card from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { onMount, onDestroy } from 'svelte';
	import { useQueryClient } from '@tanstack/svelte-query';
	import {
		Mail,
		CheckCircle2,
		XCircle,
		ExternalLink,
		AlertCircle,
		Inbox
	} from 'lucide-svelte';

	const queryClient = useQueryClient();

	// Queries
	const statusQuery = createQuery(() => ({
		queryKey: ['newsletters', 'status'],
		queryFn: () => api.getNewsletterStatus()
	}));

	// Refetch status when window regains focus (after OAuth popup completes)
	function handleFocus() {
		queryClient.invalidateQueries({ queryKey: ['newsletters', 'status'] });
	}

	onMount(() => {
		window.addEventListener('focus', handleFocus);
	});

	onDestroy(() => {
		window.removeEventListener('focus', handleFocus);
	});

	function handleConnect() {
		// Open OAuth flow in new window
		window.open(api.getOAuthStartUrl(), '_blank', 'width=600,height=700');
	}
</script>

<svelte:head>
	<title>Newsletters - Ghostwriter</title>
</svelte:head>

<div class="space-y-6">
	<div>
		<h1 class="text-2xl font-bold tracking-tight">Newsletters</h1>
		<p class="text-muted-foreground">Connect Gmail to include newsletters in your digests</p>
	</div>

	<!-- Connection Status -->
	<Card.Root>
		<Card.Header>
			<Card.Title class="flex items-center gap-2">
				<Mail class="h-5 w-5" />
				Gmail Integration
			</Card.Title>
			<Card.Description>
				Connect your Gmail account to automatically include newsletter emails in your digests
			</Card.Description>
		</Card.Header>
		<Card.Content>
			{#if statusQuery.isPending}
				<div class="space-y-4">
					<Skeleton class="h-12 w-full" />
					<Skeleton class="h-4 w-48" />
				</div>
			{:else if statusQuery.error}
				<div class="flex items-center gap-2 text-destructive">
					<AlertCircle class="h-5 w-5" />
					<span>Failed to load status</span>
				</div>
			{:else if statusQuery.data?.configured}
				<div class="space-y-4">
						<div class="flex items-center gap-3 rounded-lg border border-success/30 bg-success/10 p-4">
							<CheckCircle2 class="h-6 w-6 text-success" />
							<div>
								<p class="font-medium text-success">Gmail Connected</p>
								<p class="text-sm text-success/90">
									Your newsletters will be included in digests
								</p>
							</div>
						</div>

					<div class="rounded-lg border p-4 space-y-2">
						<div class="flex items-center gap-2 text-sm">
							<Inbox class="h-4 w-4 text-muted-foreground" />
							<span class="text-muted-foreground">Gmail Label:</span>
							<Badge variant="secondary">{statusQuery.data.label}</Badge>
						</div>
						<p class="text-sm text-muted-foreground">
							Emails with this label will be processed as newsletters
						</p>
					</div>

					<Button variant="outline" onclick={handleConnect}>
						<ExternalLink class="mr-2 h-4 w-4" />
						Re-authorize Gmail
					</Button>
				</div>
			{:else if statusQuery.data?.oauth_ready}
				<div class="space-y-4">
						<div class="flex items-center gap-3 rounded-lg border border-warning/30 bg-warning/10 p-4">
							<AlertCircle class="h-6 w-6 text-warning" />
							<div>
								<p class="font-medium text-warning">Gmail Not Connected</p>
								<p class="text-sm text-warning/90">
									Connect your Gmail to include newsletters
								</p>
							</div>
						</div>

					<Button onclick={handleConnect}>
						<Mail class="mr-2 h-4 w-4" />
						Connect Gmail
					</Button>
				</div>
			{:else}
				<div class="flex items-center gap-3 rounded-lg border border-muted p-4">
					<XCircle class="h-6 w-6 text-muted-foreground" />
					<div>
						<p class="font-medium">Gmail Integration Unavailable</p>
						<p class="text-sm text-muted-foreground">
							Gmail OAuth credentials are not configured on the server
						</p>
					</div>
				</div>
			{/if}
		</Card.Content>
	</Card.Root>

	<!-- Setup Instructions -->
	<Card.Root>
		<Card.Header>
			<Card.Title>How It Works</Card.Title>
		</Card.Header>
		<Card.Content class="space-y-4">
			<div class="grid gap-4 md:grid-cols-3">
				<div class="flex gap-3">
					<div class="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary font-semibold text-sm">
						1
					</div>
					<div>
						<p class="font-medium">Connect Gmail</p>
						<p class="text-sm text-muted-foreground">
							Authorize Ghostwriter to read your emails
						</p>
					</div>
				</div>
				<div class="flex gap-3">
					<div class="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary font-semibold text-sm">
						2
					</div>
					<div>
						<p class="font-medium">Label Newsletters</p>
						<p class="text-sm text-muted-foreground">
							Apply the "{statusQuery.data?.label || 'Ghostwriter'}" label to newsletter emails
						</p>
					</div>
				</div>
				<div class="flex gap-3">
					<div class="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary font-semibold text-sm">
						3
					</div>
					<div>
						<p class="font-medium">Automatic Processing</p>
						<p class="text-sm text-muted-foreground">
							Labeled emails are automatically included in your digests
						</p>
					</div>
				</div>
			</div>

			<div class="rounded-lg bg-muted/50 p-4 text-sm">
				<p class="font-medium mb-2">💡 Pro Tip</p>
				<p class="text-muted-foreground">
					Create a Gmail filter to automatically apply the label to emails from your favorite
					newsletter senders. This way, they'll be included in your digests without manual
					labeling.
				</p>
			</div>
		</Card.Content>
	</Card.Root>

	<!-- Privacy Note -->
	<Card.Root>
		<Card.Header>
			<Card.Title>Privacy & Security</Card.Title>
		</Card.Header>
		<Card.Content class="text-sm text-muted-foreground space-y-2">
			<p>
				Ghostwriter only reads emails that have the specific newsletter label applied.
				Your other emails are never accessed.
			</p>
			<p>
				Email content is processed locally on your server and is not sent to any
				third parties except the configured AI provider for summarization (if enabled).
			</p>
			<p>
				You can revoke access at any time by disconnecting the integration or from
				your Google Account settings.
			</p>
		</Card.Content>
	</Card.Root>
</div>
