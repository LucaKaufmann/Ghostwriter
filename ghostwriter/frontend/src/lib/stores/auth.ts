import { writable, derived } from 'svelte/store';
import { api, ApiError } from '$lib/api';
import type { HealthResponse, UserResponse, AuthStatus } from '$lib/api';

interface AuthState {
	isAuthenticated: boolean;
	isLoading: boolean;
	error: string | null;
	serverStatus: HealthResponse | null;
	authStatus: AuthStatus | null;
	user: UserResponse | null;
}

function createAuthStore() {
	const { subscribe, set, update } = writable<AuthState>({
		isAuthenticated: false,
		isLoading: true,
		error: null,
		serverStatus: null,
		authStatus: null,
		user: null
	});

	return {
		subscribe,

		// Initialize auth state from localStorage
		async init() {
			console.log('[auth] init called');
			update((state) => ({ ...state, isLoading: true, error: null }));

			// Check server health first
			try {
				const health = await api.getHealth();
				console.log('[auth] health check passed');
				update((state) => ({ ...state, serverStatus: health }));
			} catch {
				console.log('[auth] health check failed, bailing');
				update((state) => ({
					...state,
					serverStatus: null,
					isLoading: false,
					error: 'Cannot connect to server'
				}));
				return;
			}

			// Check auth status (setup complete?)
			try {
				const authStatus = await api.getAuthStatus();
				console.log('[auth] auth status:', authStatus);
				update((state) => ({ ...state, authStatus }));
			} catch {
				console.log('[auth] auth status check failed');
				update((state) => ({ ...state, authStatus: null }));
			}

			// Check if we have a stored token
			const token = api.getToken();
			console.log('[auth] stored token exists:', !!token);

			if (token) {
				// Verify token by making an authenticated request
				try {
					const user = await api.getCurrentUser();
					console.log('[auth] token verified, user:', user?.username);
					update((state) => ({
						...state,
						isAuthenticated: true,
						isLoading: false,
						user
					}));
				} catch (err) {
					if (err instanceof ApiError && err.isUnauthorized) {
						// Token is invalid
						console.log('[auth] token invalid (401/403), clearing');
						api.setToken(null);
						update((state) => ({
							...state,
							isAuthenticated: false,
							isLoading: false,
							user: null,
							error: 'Session expired. Please log in again.'
						}));
					} else {
						// Network error or server issue - keep token, try again later
						console.log('[auth] token verify failed (network?), keeping token');
						update((state) => ({
							...state,
							isAuthenticated: true,
							isLoading: false,
							error: 'Could not verify session'
						}));
					}
				}
			} else {
				console.log('[auth] no token, showing login');
				update((state) => ({
					...state,
					isAuthenticated: false,
					isLoading: false,
					user: null
				}));
			}
		},

		// Login with username and password
		async loginWithCredentials(username: string, password: string) {
			console.log('[auth] loginWithCredentials called');
			update((state) => ({ ...state, error: null }));

			try {
				console.log('[auth] calling api.login...');
				const response = await api.login({ username, password });
				console.log('[auth] api.login returned:', { hasToken: !!response?.access_token, hasUser: !!response?.user });
				api.setToken(response.access_token);
				console.log('[auth] token stored, updating state to authenticated');
				update((state) => ({
					...state,
					isAuthenticated: true,
					error: null,
					user: response.user
				}));
				console.log('[auth] state updated, returning true');
				return true;
			} catch (err) {
				console.error('[auth] loginWithCredentials error:', err);
				const message =
					err instanceof ApiError
						? err.message
						: 'Could not connect to server';
				update((state) => ({
					...state,
					isAuthenticated: false,
					error: message,
					user: null
				}));
				return false;
			}
		},

		// Register first admin user
		async register(username: string, password: string, email?: string) {
			update((state) => ({ ...state, error: null }));

			try {
				const response = await api.register({ username, password, email });
				api.setToken(response.access_token);
				update((state) => ({
					...state,
					isAuthenticated: true,
					error: null,
					user: response.user,
					authStatus: { setup_complete: true, registration_open: false }
				}));
				return true;
			} catch (err) {
				const message =
					err instanceof ApiError
						? err.message
						: 'Could not connect to server';
				update((state) => ({
					...state,
					isAuthenticated: false,
					error: message,
					user: null
				}));
				return false;
			}
		},

		// Legacy: Set auth token directly (for backward compatibility with old API_KEY flow)
		async loginWithToken(token: string) {
			update((state) => ({ ...state, error: null }));

			api.setToken(token);

			try {
				// Verify token works - try to get user, fall back to config check
				try {
					const user = await api.getCurrentUser();
					update((state) => ({
						...state,
						isAuthenticated: true,
						error: null,
						user
					}));
				} catch {
					// Legacy API_KEY might not have a user - just verify it works
					await api.getClientConfig();
					update((state) => ({
						...state,
						isAuthenticated: true,
						error: null,
						user: null
					}));
				}
				return true;
			} catch (err) {
				api.setToken(null);
				const message =
					err instanceof ApiError && err.isUnauthorized
						? 'Invalid token'
						: 'Could not connect to server';
				update((state) => ({
					...state,
					isAuthenticated: false,
					error: message,
					user: null
				}));
				return false;
			}
		},

		// Clear auth token
		logout() {
			api.setToken(null);
			set({
				isAuthenticated: false,
				isLoading: false,
				error: null,
				serverStatus: null,
				authStatus: null,
				user: null
			});
		},

		// Clear error
		clearError() {
			update((state) => ({ ...state, error: null }));
		},

		// Check server health
		async checkHealth() {
			try {
				const health = await api.getHealth();
				update((state) => ({ ...state, serverStatus: health }));
				return health;
			} catch {
				update((state) => ({ ...state, serverStatus: null }));
				return null;
			}
		},

		// Refresh auth status
		async refreshAuthStatus() {
			try {
				const authStatus = await api.getAuthStatus();
				update((state) => ({ ...state, authStatus }));
				return authStatus;
			} catch {
				return null;
			}
		},

		// Update user info
		async updateUser(data: { email?: string; password?: string }) {
			try {
				const user = await api.updateCurrentUser(data);
				update((state) => ({ ...state, user }));
				return true;
			} catch {
				return false;
			}
		}
	};
}

export const auth = createAuthStore();

// Derived stores for convenience
export const isAuthenticated = derived(auth, ($auth) => $auth.isAuthenticated);
export const isLoading = derived(auth, ($auth) => $auth.isLoading);
export const authError = derived(auth, ($auth) => $auth.error);
export const serverStatus = derived(auth, ($auth) => $auth.serverStatus);
export const authStatus = derived(auth, ($auth) => $auth.authStatus);
export const currentUser = derived(auth, ($auth) => $auth.user);
