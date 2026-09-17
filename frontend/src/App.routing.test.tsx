import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, useLocation } from 'react-router-dom';
import App from './App';

const auth = vi.hoisted(() => ({ ready: true, user: { name: 'Tester' } as { name: string } | null, error: null, config: { mode: 'demo' }, signOut: vi.fn() }));
vi.mock('./auth', () => ({ useAuth: () => auth }));
vi.mock('@tanstack/react-query', () => ({ useQuery: () => ({ data: undefined }) }));
vi.mock('./components/OnboardingTour', () => ({ OnboardingTour: () => null, replayTour: vi.fn() }));
vi.mock('./pages/TodayPage', () => ({ default: () => <h1>Today view</h1> }));
vi.mock('./pages/BoardPage', () => ({ default: () => <h1>Pipeline view</h1> }));
vi.mock('./pages/NudgesPage', () => ({ default: () => <h1>Nudges view</h1> }));
vi.mock('./pages/ImportPage', () => ({ default: () => <h1>Import view</h1> }));
vi.mock('./pages/AnalyticsPage', () => ({ default: () => <h1>Analytics view</h1> }));
vi.mock('./pages/ProfilePage', () => ({ default: () => <h1>Profile view</h1> }));
vi.mock('./pages/LoginPage', () => ({ default: () => <h1>Sign in view</h1> }));
function Location() { const l = useLocation(); return <output aria-label="Current route">{l.pathname}{l.search}</output>; }
function mount(path = '/') { return render(<MemoryRouter initialEntries={[path]}><App /><Location /></MemoryRouter>); }
afterEach(() => { cleanup(); auth.ready = true; auth.user = { name: 'Tester' }; });
describe('application routing', () => {
  it.each([['/','Today'],['/pipeline?app=42','Pipeline'],['/nudges','Nudges'],['/import','Import'],['/analytics','Analytics'],['/profile','Profile']])('opens the %s deep link', (path, label) => {
    mount(path); expect(screen.getByRole('heading', { name: `${label} view` })).toBeTruthy();
    expect(screen.getByRole('status', { name: 'Current route' }).textContent).toBe(path);
  });
  it('keeps the sidebar, active link, and query string synchronized through navigation', async () => {
    mount('/pipeline?app=42');
    expect(screen.getByRole('link', { name: 'Pipeline' }).getAttribute('aria-current')).toBe('page');
    fireEvent.click(screen.getByRole('link', { name: 'Nudges' }));
    await screen.findByRole('heading', { name: 'Nudges view' });
    expect(screen.getByRole('status', { name: 'Current route' }).textContent).toBe('/nudges');
    expect(screen.getByRole('link', { name: 'Nudges' }).getAttribute('aria-current')).toBe('page');
    expect(screen.getByRole('link', { name: 'Pipeline' }).getAttribute('aria-current')).toBeNull();
  });
  it('closes the mobile menu after a route is chosen', async () => {
    mount(); fireEvent.click(screen.getByRole('button', { name: 'Open menu' }));
    fireEvent.click(screen.getAllByRole('link', { name: 'Pipeline' })[1]);
    await screen.findByRole('heading', { name: 'Pipeline view' });
    expect(screen.queryByRole('button', { name: 'Close menu' })).toBeNull();
  });
  it('redirects unknown routes to today', async () => {
    mount('/missing/nested'); await screen.findByRole('heading', { name: 'Today view' });
    await waitFor(() => expect(screen.getByRole('status', { name: 'Current route' }).textContent).toBe('/'));
  });
  it('does not expose protected views to a signed-out visitor', () => {
    auth.user = null; mount('/pipeline?app=42');
    expect(screen.getByRole('heading', { name: 'Sign in view' })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Pipeline view' })).toBeNull();
  });
  it('waits for authentication before rendering protected routes', () => {
    auth.ready = false; mount('/pipeline'); expect(screen.getByText('Warming up OfferLoop…')).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Pipeline view' })).toBeNull();
  });
});
