const mockAuth = {
  getSession: jest.fn(),
  refreshSession: jest.fn(),
  setSession: jest.fn(),
  signOut: jest.fn(),
  onAuthStateChange: jest.fn(() => ({
    data: { subscription: { unsubscribe: jest.fn() } },
  })),
};

const mockClient = { auth: mockAuth };

module.exports = {
  createClient: jest.fn(() => mockClient),
  __mockClient: mockClient,
  __mockAuth: mockAuth,
};
