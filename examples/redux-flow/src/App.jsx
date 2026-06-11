import React, { useState } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { increment, decrement, incrementByAmount, setName } from './store.js';

function App() {
  const count = useSelector((state) => state.counter.value);
  const name = useSelector((state) => state.user.name);
  const dispatch = useDispatch();
  const [inputName, setInputName] = useState('');

  const handleUpdateName = (e) => {
    e.preventDefault();
    if (inputName.trim()) {
      dispatch(setName(inputName));
      setInputName('');
    }
  };

  return (
    <div style={{ fontFamily: 'sans-serif', padding: '40px', maxWidth: '600px', margin: '0 auto' }}>
      <h1>Redux Integration Flow</h1>
      <p>This demo application integrates Redux Toolkit state via <code>bridgeRedux</code>.</p>
      
      <div style={{ border: '1px solid #ccc', padding: '20px', borderRadius: '8px', marginBottom: '20px' }}>
        <h2>Counter Slice</h2>
        <p style={{ fontSize: '24px' }}>Count: <strong id="counter-value">{count}</strong></p>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button id="btn-increment" onClick={() => dispatch(increment())} style={{ padding: '10px 20px' }}>
            Increment
          </button>
          <button id="btn-decrement" onClick={() => dispatch(decrement())} style={{ padding: '10px 20px' }}>
            Decrement
          </button>
          <button id="btn-add-three" onClick={() => dispatch(incrementByAmount(3))} style={{ padding: '10px 20px' }}>
            +3
          </button>
        </div>
      </div>

      <div style={{ border: '1px solid #ccc', padding: '20px', borderRadius: '8px' }}>
        <h2>User Slice</h2>
        <p>Name: <strong id="user-name">{name}</strong></p>
        <form onSubmit={handleUpdateName} style={{ display: 'flex', gap: '10px' }}>
          <input
            type="text"
            id="input-name"
            placeholder="New Name..."
            value={inputName}
            onChange={(e) => setInputName(e.target.value)}
            style={{ padding: '8px', flex: 1 }}
          />
          <button type="submit" id="btn-update-name" style={{ padding: '8px 16px' }}>
            Set Name
          </button>
        </form>
      </div>
    </div>
  );
}

export default App;
