const mockAuth = {
  getSession: jest.fn(),
  refreshSession: jest.fn(),
  setSession: jest.fn(),
  signOut: jest.fn(),
  onAuthStateChange: jest.fn(() => ({
    data: { subscription: { id: 'mock-subscription-id', callback: jest.fn(), unsubscribe: jest.fn() } },
  })),
};

const mockClient = { auth: mockAuth };

module.exports = {
  createClient: jest.fn(() => mockClient),
  __mockClient: mockClient,
  __mockAuth: mockAuth,
};
