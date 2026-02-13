<script lang="ts">
	import { page } from '$app/stores';
	import { createMutation } from '@tanstack/svelte-query';
	import { api } from '$lib/api';
	import { auth, serverStatus } from '$lib/stores/auth';
	import ThemeToggle from '$lib/components/layout/ThemeToggle.svelte';
	import { Button } from '$lib/components/ui/button';
	import { Separator } from '$lib/components/ui/separator';
	import * as Sheet from '$lib/components/ui/sheet';
	import { toast } from 'svelte-sonner';
	import {
		BookCopy,
		BookOpen,
		ChevronRight,
		LayoutDashboard,
		LogOut,
		Mail,
		Menu,
		Play,
		Rss,
		Settings
	} from 'lucide-svelte';

	let { children } = $props();
	let mobileMenuOpen = $state(false);

	const navItems = [
		{ href: '/', label: 'Dashboard', icon: LayoutDashboard },
		{ href: '/feeds', label: 'Feeds', icon: Rss },
		{ href: '/digests', label: 'Digests', icon: BookCopy },
		{ href: '/newsletters', label: 'Newsletters', icon: Mail },
		{ href: '/settings', label: 'Settings', icon: Settings }
	];

	const quickDigestMutation = createMutation(() => ({
		mutationFn: () => api.triggerDigest(),
		onSuccess: () => {
			toast.success('Digest generation started');
		},
		onError: (error: Error) => {
			toast.error('Failed to trigger digest', {
				description: error.message ?? 'Unknown error'
			});
		}
	}));

	function isActive(href: string): boolean {
		if (href === '/') return $page.url.pathname === '/';
		return $page.url.pathname.startsWith(href);
	}

	const activeNavItem = $derived.by(() => navItems.find((item) => isActive(item.href)) ?? navItems[0]);

	function handleLogout() {
		auth.logout();
	}

	function closeMobileMenu() {
		mobileMenuOpen = false;
	}

	function triggerDigest() {
		quickDigestMutation.mutate();
	}
</script>

<div class="flex min-h-screen w-full max-w-full overflow-x-hidden bg-background">
	<aside class="hidden w-72 flex-shrink-0 border-r bg-card lg:block">
		<div class="flex h-full flex-col">
			<div class="flex h-16 items-center justify-between border-b px-5">
				<div class="flex items-center gap-2">
					<BookOpen class="h-6 w-6 text-primary" />
					<span class="font-semibold">Ghostwriter</span>
				</div>
				<ThemeToggle size="sm" />
			</div>

			<div class="border-b p-4">
				<Button class="w-full justify-start" onclick={triggerDigest} disabled={quickDigestMutation.isPending}>
					{#if quickDigestMutation.isPending}
						<Play class="mr-2 h-4 w-4 animate-pulse" />
						Starting...
					{:else}
						<Play class="mr-2 h-4 w-4" />
						Generate Digest
					{/if}
				</Button>
			</div>

			<nav class="flex-1 space-y-1 p-4">
				{#each navItems as item}
					<a
						href={item.href}
						aria-current={isActive(item.href) ? 'page' : undefined}
						class="group flex items-center gap-3 rounded-lg border px-3 py-2 text-sm font-medium transition-colors {isActive(
							item.href
						)
							? 'border-primary/30 bg-primary/10 text-primary'
							: 'border-transparent text-muted-foreground hover:border-border hover:bg-accent hover:text-accent-foreground'}"
					>
						<item.icon class="h-4 w-4" />
						{item.label}
						{#if isActive(item.href)}
							<span class="ml-auto h-2 w-2 rounded-full bg-primary" aria-hidden="true"></span>
						{/if}
					</a>
				{/each}
			</nav>

			<div class="border-t p-4">
				{#if $serverStatus}
					<p class="mb-3 text-xs text-muted-foreground">v{$serverStatus.version} • {$serverStatus.ai_provider}</p>
				{/if}
				<Button variant="ghost" class="w-full justify-start" onclick={handleLogout}>
					<LogOut class="mr-2 h-4 w-4" />
					Logout
				</Button>
			</div>
		</div>
	</aside>

	<div class="flex min-w-0 flex-1 flex-col">
		<header class="flex h-16 items-center justify-between border-b px-4 lg:hidden">
			<div class="min-w-0">
				<p class="text-xs text-muted-foreground">Current section</p>
				<p class="truncate text-sm font-semibold">{activeNavItem.label}</p>
			</div>
			<div class="flex items-center gap-2">
				<Button variant="outline" size="sm" onclick={triggerDigest} disabled={quickDigestMutation.isPending}>
					<Play class="mr-2 h-4 w-4" />
					Digest
				</Button>
				<ThemeToggle size="sm" />
				<Sheet.Root bind:open={mobileMenuOpen}>
					<Sheet.Trigger>
						{#snippet child({ props })}
							<Button {...props} variant="ghost" size="icon">
								<Menu class="h-5 w-5" />
								<span class="sr-only">Open menu</span>
							</Button>
						{/snippet}
					</Sheet.Trigger>
					<Sheet.Content side="right" class="w-72 p-0">
						<Sheet.Header class="border-b px-6 py-4">
							<Sheet.Title class="flex items-center gap-2">
								<BookOpen class="h-5 w-5 text-primary" />
								Ghostwriter
							</Sheet.Title>
						</Sheet.Header>

						<div class="border-b p-4">
							<Button class="w-full justify-start" onclick={triggerDigest} disabled={quickDigestMutation.isPending}>
								<Play class="mr-2 h-4 w-4" />
								Generate Digest
							</Button>
						</div>

						<nav class="flex-1 space-y-1 p-4">
							{#each navItems as item}
								<a
									href={item.href}
									onclick={closeMobileMenu}
									aria-current={isActive(item.href) ? 'page' : undefined}
									class="flex items-center gap-3 rounded-lg border px-3 py-3 text-sm font-medium transition-colors {isActive(
										item.href
									)
										? 'border-primary/30 bg-primary/10 text-primary'
										: 'border-transparent text-muted-foreground hover:border-border hover:bg-accent hover:text-accent-foreground'}"
								>
									<item.icon class="h-4 w-4" />
									{item.label}
									<ChevronRight class="ml-auto h-4 w-4" />
								</a>
							{/each}
						</nav>

						<Separator />

						<div class="p-4">
							<div class="mb-3">
								<ThemeToggle showLabel />
							</div>
							{#if $serverStatus}
								<p class="mb-2 text-xs text-muted-foreground">v{$serverStatus.version} • {$serverStatus.ai_provider}</p>
							{/if}
							<Button variant="ghost" class="w-full justify-start" onclick={handleLogout}>
								<LogOut class="mr-2 h-4 w-4" />
								Logout
							</Button>
						</div>
					</Sheet.Content>
				</Sheet.Root>
			</div>
		</header>

		<header class="hidden h-16 items-center justify-between border-b px-6 lg:flex">
			<div>
				<p class="text-xs text-muted-foreground">Current section</p>
				<p class="text-sm font-semibold">{activeNavItem.label}</p>
			</div>
			<div class="flex items-center gap-2">
				<Button variant="outline" size="sm" onclick={triggerDigest} disabled={quickDigestMutation.isPending}>
					<Play class="mr-2 h-4 w-4" />
					Generate Digest
				</Button>
				<ThemeToggle size="sm" />
			</div>
		</header>

		<main class="min-w-0 flex-1 overflow-y-auto">
			<div class="mx-auto max-w-7xl p-4 md:p-6 lg:p-8">
				{@render children()}
			</div>
		</main>
	</div>
</div>
