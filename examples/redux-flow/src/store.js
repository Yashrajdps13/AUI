import { createSlice, configureStore } from '@reduxjs/toolkit';
import { bridgeRedux } from 'react-agent-bridge/redux';

const counterSlice = createSlice({
  name: 'counter',
  initialState: { value: 0 },
  reducers: {
    increment: (state) => {
      state.value += 1;
    },
    decrement: (state) => {
      state.value -= 1;
    },
    incrementByAmount: (state, action) => {
      state.value += action.payload;
    },
  },
});

const userSlice = createSlice({
  name: 'user',
  initialState: { name: 'Developer' },
  reducers: {
    setName: (state, action) => {
      state.name = action.payload;
    },
  },
});

export const { increment, decrement, incrementByAmount } = counterSlice.actions;
export const { setName } = userSlice.actions;

const metadata = {
  counter: { description: 'Simple global click counter slice' },
  user: { sensitive: false, description: 'User profile details containing developer name' },
};

export const store = bridgeRedux(
  configureStore({
    reducer: {
      counter: counterSlice.reducer,
      user: userSlice.reducer,
    },
  }),
  metadata,
  'ReduxStore'
);
