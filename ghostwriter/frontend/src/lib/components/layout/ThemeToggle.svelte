<script lang="ts">
	import { Monitor, Moon, Sun } from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import { theme, type ThemePreference } from '$lib/stores/theme';

	interface Props {
		size?: 'sm' | 'default';
		showLabel?: boolean;
	}

	let { size = 'default', showLabel = false }: Props = $props();

	const themeOptions: Array<{ value: ThemePreference; label: string; icon: typeof Sun }> = [
		{ value: 'light', label: 'Light', icon: Sun },
		{ value: 'dark', label: 'Dark', icon: Moon },
		{ value: 'system', label: 'System', icon: Monitor }
	];

	const selectedOption = $derived.by(() => {
		const preference = theme.preference;
		return themeOptions.find((option) => option.value === preference) ?? themeOptions[2];
	});

	function updateTheme(preference: ThemePreference) {
		theme.setPreference(preference);
	}
</script>

<DropdownMenu.Root>
	<DropdownMenu.Trigger>
		{#snippet child({ props })}
			<Button
				{...props}
				variant="outline"
				size={size === 'sm' ? 'sm' : 'default'}
				aria-label="Change theme"
			>
				<selectedOption.icon class="h-4 w-4" />
				{#if showLabel}
					<span class="ml-2">{selectedOption.label}</span>
				{/if}
			</Button>
		{/snippet}
	</DropdownMenu.Trigger>
	<DropdownMenu.Content align="end">
		{#each themeOptions as option}
			<DropdownMenu.Item onclick={() => updateTheme(option.value)}>
				<option.icon class="mr-2 h-4 w-4" />
				{option.label}
				{#if theme.preference === option.value}
					<span class="ml-auto text-xs text-muted-foreground">Active</span>
				{/if}
			</DropdownMenu.Item>
		{/each}
	</DropdownMenu.Content>
</DropdownMenu.Root>
