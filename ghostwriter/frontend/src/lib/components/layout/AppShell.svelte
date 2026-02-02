<script lang="ts">
	import { page } from '$app/stores';
	import { Button } from '$lib/components/ui/button';
	import * as Sheet from '$lib/components/ui/sheet';
	import { Separator } from '$lib/components/ui/separator';
	import { auth, serverStatus } from '$lib/stores/auth';
	import {
		BookOpen,
		LayoutDashboard,
		Rss,
		BookCopy,
		Mail,
		Settings,
		Menu,
		LogOut,
		ChevronRight
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

	function isActive(href: string): boolean {
		if (href === '/') return $page.url.pathname === '/';
		return $page.url.pathname.startsWith(href);
	}

	function handleLogout() {
		auth.logout();
	}

	function closeMobileMenu() {
		mobileMenuOpen = false;
	}
</script>

<div class="flex min-h-screen">
	<!-- Desktop Sidebar -->
	<aside class="hidden w-64 flex-shrink-0 border-r bg-card lg:block">
		<div class="flex h-full flex-col">
			<!-- Logo -->
			<div class="flex h-16 items-center gap-2 border-b px-6">
				<BookOpen class="h-6 w-6 text-primary" />
				<span class="font-semibold">Ghostwriter</span>
			</div>

			<!-- Navigation -->
			<nav class="flex-1 space-y-1 p-4">
				{#each navItems as item}
					<a
						href={item.href}
						class="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors {isActive(
							item.href
						)
							? 'bg-primary text-primary-foreground'
							: 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'}"
					>
						<item.icon class="h-4 w-4" />
						{item.label}
					</a>
				{/each}
			</nav>

			<!-- Footer -->
			<div class="border-t p-4">
				{#if $serverStatus}
					<p class="mb-2 text-xs text-muted-foreground">
						v{$serverStatus.version} • {$serverStatus.ai_provider}
					</p>
				{/if}
				<Button variant="ghost" class="w-full justify-start" onclick={handleLogout}>
					<LogOut class="mr-2 h-4 w-4" />
					Logout
				</Button>
			</div>
		</div>
	</aside>

	<!-- Mobile Header + Content -->
	<div class="flex flex-1 flex-col">
		<!-- Mobile Header -->
		<header class="flex h-16 items-center justify-between border-b px-4 lg:hidden">
			<div class="flex items-center gap-2">
				<BookOpen class="h-6 w-6 text-primary" />
				<span class="font-semibold">Ghostwriter</span>
			</div>

			<Sheet.Root bind:open={mobileMenuOpen}>
				<Sheet.Trigger>
					{#snippet child({ props })}
						<Button {...props} variant="ghost" size="icon">
							<Menu class="h-5 w-5" />
							<span class="sr-only">Open menu</span>
						</Button>
					{/snippet}
				</Sheet.Trigger>
				<Sheet.Content side="right" class="w-64 p-0">
					<Sheet.Header class="border-b px-6 py-4">
						<Sheet.Title class="flex items-center gap-2">
							<BookOpen class="h-5 w-5 text-primary" />
							Ghostwriter
						</Sheet.Title>
					</Sheet.Header>

					<nav class="flex-1 space-y-1 p-4">
						{#each navItems as item}
							<a
								href={item.href}
								onclick={closeMobileMenu}
								class="flex items-center gap-3 rounded-lg px-3 py-3 text-sm font-medium transition-colors {isActive(
									item.href
								)
									? 'bg-primary text-primary-foreground'
									: 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'}"
							>
								<item.icon class="h-4 w-4" />
								{item.label}
								<ChevronRight class="ml-auto h-4 w-4" />
							</a>
						{/each}
					</nav>

					<Separator />

					<div class="p-4">
						{#if $serverStatus}
							<p class="mb-2 text-xs text-muted-foreground">
								v{$serverStatus.version} • {$serverStatus.ai_provider}
							</p>
						{/if}
						<Button variant="ghost" class="w-full justify-start" onclick={handleLogout}>
							<LogOut class="mr-2 h-4 w-4" />
							Logout
						</Button>
					</div>
				</Sheet.Content>
			</Sheet.Root>
		</header>

		<!-- Main Content -->
		<main class="flex-1 overflow-auto">
			<div class="container mx-auto p-4 md:p-6 lg:p-8">
				{@render children()}
			</div>
		</main>
	</div>
</div>
