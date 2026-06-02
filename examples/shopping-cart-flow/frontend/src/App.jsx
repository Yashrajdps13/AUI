import { useState } from 'react';

// Product list options
const PRODUCTS = [
  { id: 'prod-apple', name: 'Organic Apple', price: 1.5, emoji: '🍎' },
  { id: 'prod-banana', name: 'Fresh Banana', price: 0.8, emoji: '🍌' },
  { id: 'prod-orange', name: 'Juicy Orange', price: 1.2, emoji: '🍊' },
];

/**
 * Extracted ProductCard component.
 * Gets auto-registered in the bridge, allowing the agent to target it directly for events.
 */
function ProductCard({ prod, onAdd }) {
  return (
    <div
      className="product-card"
      onClick={() => onAdd(prod)}
      id={`btn-${prod.id}`}
    >
      <div className="product-emoji">{prod.emoji}</div>
      <div className="product-name">{prod.name}</div>
      <div className="product-price">${prod.price.toFixed(2)}</div>
    </div>
  );
}

/**
 * Extracted CartItem component.
 * Auto-registered in the bridge, allowing targeted edits and events.
 */
function CartItem({ item, onUpdate }) {
  if (!item || typeof item !== 'object') return null;
  const emoji = item.emoji || '📦';
  const name = item.name || 'Product';
  const price = typeof item.price === 'number' ? item.price : 0;
  const quantity = item.quantity || 0;
  const itemId = item.id || '';

  return (
    <div className="cart-item">
      <div className="item-details">
        <span className="item-emoji">{emoji}</span>
        <div>
          <div className="item-name">{name}</div>
          <div className="item-price">${price.toFixed(2)}</div>
        </div>
      </div>
      <div className="quantity-control">
        <button
          className="qty-btn"
          onClick={() => onUpdate(itemId, -1)}
          id={`btn-minus-${itemId}`}
          disabled={!itemId}
        >
          -
        </button>
        <span>{quantity}</span>
        <button
          className="qty-btn"
          onClick={() => onUpdate(itemId, 1)}
          id={`btn-plus-${itemId}`}
          disabled={!itemId}
        >
          +
        </button>
      </div>
    </div>
  );
}

export default function App() {
  const [cart, setCart] = useState([]);
  const [coupon, setCoupon] = useState('');
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [step, setStep] = useState('cart'); // 'cart' | 'shipping' | 'complete'
  const [isCouponApplied, setIsCouponApplied] = useState(false);

  // Cart operations
  const addToCart = (product) => {
    setCart((prev) => {
      const existing = prev.find((item) => item.id === product.id);
      if (existing) {
        return prev.map((item) =>
          item.id === product.id ? { ...item, quantity: item.quantity + 1 } : item
        );
      }
      return [...prev, { ...product, quantity: 1 }];
    });
  };

  const updateQuantity = (productId, amount) => {
    setCart((prev) => {
      return prev
        .map((item) => {
          if (item.id === productId) {
            const nextQty = item.quantity + amount;
            return nextQty > 0 ? { ...item, quantity: nextQty } : null;
          }
          return item;
        })
        .filter(Boolean);
    });
  };

  // Pricing calculations
  const subtotal = cart.reduce((sum, item) => {
    const price = item && typeof item.price === 'number' ? item.price : 0;
    const qty = item && typeof item.quantity === 'number' ? item.quantity : 0;
    return sum + price * qty;
  }, 0);
  const discount = isCouponApplied ? subtotal * 0.1 : 0;
  const total = subtotal - discount;

  const handleApplyCoupon = () => {
    if (coupon.trim().toUpperCase() === 'SAVE10') {
      setIsCouponApplied(true);
    } else {
      alert('Invalid coupon! Try "SAVE10".');
    }
  };

  return (
    <div className="app-container">
      {/* Dynamic CSS Styling Injector */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap');
        
        * {
          box-sizing: border-box;
          margin: 0;
          padding: 0;
        }

        body {
          background: radial-gradient(circle at 50% 50%, #151829 0%, #090a0f 100%);
          font-family: 'Outfit', sans-serif;
          color: #f1f3f9;
          min-height: 100vh;
          display: flex;
          justify-content: center;
          align-items: center;
          padding: 20px;
        }

        .app-container {
          background: rgba(20, 24, 43, 0.65);
          backdrop-filter: blur(16px);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 24px;
          width: 100%;
          max-width: 900px;
          min-height: 550px;
          display: grid;
          grid-template-columns: 1.2fr 0.8fr;
          overflow: hidden;
          box-shadow: 0 20px 50px rgba(0, 0, 0, 0.4), 0 0 100px rgba(99, 102, 241, 0.15);
        }

        @media (max-width: 768px) {
          .app-container {
            grid-template-columns: 1fr;
          }
        }

        .main-panel {
          padding: 40px;
          display: flex;
          flex-direction: column;
        }

        .summary-panel {
          background: rgba(255, 255, 255, 0.02);
          border-left: 1px solid rgba(255, 255, 255, 0.05);
          padding: 40px;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
        }

        h2 {
          font-size: 28px;
          font-weight: 800;
          margin-bottom: 24px;
          background: linear-gradient(135deg, #a5b4fc 0%, #6366f1 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
        }

        h3 {
          font-size: 20px;
          font-weight: 600;
          margin-bottom: 16px;
        }

        .product-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
          gap: 16px;
          margin-bottom: 30px;
        }

        .product-card {
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 16px;
          padding: 16px;
          text-align: center;
          cursor: pointer;
          transition: all 0.3s ease;
        }

        .product-card:hover {
          background: rgba(99, 102, 241, 0.1);
          border-color: rgba(99, 102, 241, 0.3);
          transform: translateY(-4px);
          box-shadow: 0 10px 20px rgba(99, 102, 241, 0.1);
        }

        .product-emoji {
          font-size: 32px;
          margin-bottom: 8px;
        }

        .product-name {
          font-size: 14px;
          font-weight: 600;
          margin-bottom: 4px;
        }

        .product-price {
          color: #a5b4fc;
          font-size: 13px;
        }

        .cart-items {
          flex-grow: 1;
          display: flex;
          flex-direction: column;
          gap: 12px;
          margin-bottom: 24px;
          max-height: 250px;
          overflow-y: auto;
        }

        .cart-item {
          display: flex;
          justify-content: space-between;
          align-items: center;
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.04);
          border-radius: 12px;
          padding: 12px 16px;
        }

        .item-details {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .item-emoji {
          font-size: 24px;
        }

        .item-name {
          font-size: 15px;
          font-weight: 600;
        }

        .item-price {
          color: #94a3b8;
          font-size: 13px;
        }

        .quantity-control {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .qty-btn {
          width: 24px;
          height: 24px;
          border-radius: 6px;
          border: none;
          background: rgba(255, 255, 255, 0.1);
          color: white;
          cursor: pointer;
          font-weight: bold;
          font-size: 14px;
          display: flex;
          justify-content: center;
          align-items: center;
          transition: background 0.2s;
        }

        .qty-btn:hover {
          background: #6366f1;
        }

        .form-group {
          margin-bottom: 20px;
        }

        .form-group label {
          display: block;
          font-size: 13px;
          color: #94a3b8;
          margin-bottom: 8px;
          font-weight: 600;
        }

        .form-input {
          width: 100%;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 12px;
          padding: 14px 16px;
          color: white;
          font-family: inherit;
          font-size: 15px;
          outline: none;
          transition: border-color 0.3s;
        }

        .form-input:focus {
          border-color: #6366f1;
        }

        .coupon-box {
          display: flex;
          gap: 10px;
          margin-bottom: 20px;
        }

        .btn {
          background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
          color: white;
          border: none;
          padding: 14px 24px;
          border-radius: 12px;
          font-family: inherit;
          font-weight: 600;
          font-size: 15px;
          cursor: pointer;
          width: 100%;
          transition: all 0.3s;
          box-shadow: 0 4px 15px rgba(99, 102, 241, 0.3);
        }

        .btn:hover {
          transform: translateY(-2px);
          box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5);
        }

        .btn-secondary {
          background: rgba(255, 255, 255, 0.05);
          color: #f1f3f9;
          box-shadow: none;
          border: 1px solid rgba(255, 255, 255, 0.08);
        }

        .btn-secondary:hover {
          background: rgba(255, 255, 255, 0.1);
          box-shadow: none;
        }

        .coupon-btn {
          width: auto;
          padding: 0 20px;
        }

        .pricing-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
          padding-bottom: 20px;
          margin-bottom: 20px;
        }

        .pricing-row {
          display: flex;
          justify-content: space-between;
          font-size: 15px;
          color: #94a3b8;
        }

        .pricing-row.total {
          font-size: 18px;
          font-weight: 800;
          color: white;
        }

        .empty-cart-msg {
          text-align: center;
          color: #64748b;
          padding: 40px 0;
          font-style: italic;
        }

        .coupon-success {
          color: #10b981;
          font-size: 13px;
          font-weight: 600;
          margin-top: 4px;
        }
      `}</style>

      {/* Main Panel */}
      <div className="main-panel">
        {step === 'cart' && (
          <>
            <h2>Choose Products</h2>
            <div className="product-grid">
              {PRODUCTS.map((prod) => (
                <ProductCard key={prod.id} prod={prod} onAdd={addToCart} />
              ))}
            </div>

            <h3>Your Cart</h3>
            <div className="cart-items">
              {cart.length === 0 ? (
                <div className="empty-cart-msg">Your cart is empty. Click products to add.</div>
              ) : (
                cart.map((item, idx) => (
                  <CartItem
                    key={item && item.id ? item.id : `item-${idx}`}
                    item={item}
                    onUpdate={updateQuantity}
                  />
                ))
              )}
            </div>

            {cart.length > 0 && (
              <button
                className="btn"
                onClick={() => setStep('shipping')}
                id="btn-go-to-checkout"
              >
                Proceed to Shipping
              </button>
            )}
          </>
        )}

        {step === 'shipping' && (
          <>
            <h2>Shipping Details</h2>
            <div className="form-group">
              <label htmlFor="fullName">Full Name</label>
              <input
                id="fullName"
                type="text"
                className="form-input"
                placeholder="John Doe"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
              />
            </div>
            <div className="form-group">
              <label htmlFor="email">Email Address</label>
              <input
                id="email"
                type="text"
                className="form-input"
                placeholder="john@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <div style={{ display: 'flex', gap: '16px', marginTop: '20px' }}>
              <button
                className="btn btn-secondary"
                onClick={() => setStep('cart')}
                id="btn-back"
              >
                Back to Cart
              </button>
              <button
                className="btn"
                onClick={() => setStep('complete')}
                id="btn-submit-order"
              >
                Place Order
              </button>
            </div>
          </>
        )}

        {step === 'complete' && (
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <div style={{ fontSize: '64px', marginBottom: '20px' }}>🎉</div>
            <h2>Order Placed Successfully!</h2>
            <p style={{ color: '#94a3b8', marginBottom: '30px' }}>
              Thank you for shopping, {fullName || 'customer'}! We sent a receipt to {email || 'your email'}.
            </p>
            <button
              className="btn"
              onClick={() => {
                setCart([]);
                setCoupon('');
                setFullName('');
                setEmail('');
                setIsCouponApplied(false);
                setStep('cart');
              }}
              id="btn-start-over"
            >
              Shop Again
            </button>
          </div>
        )}
      </div>

      {/* Summary Panel */}
      <div className="summary-panel">
        <div>
          <h3>Order Summary</h3>
          <div className="pricing-list">
            <div className="pricing-row">
              <span>Subtotal</span>
              <span>${subtotal.toFixed(2)}</span>
            </div>
            <div className="pricing-row">
              <span>Discount</span>
              <span>-${discount.toFixed(2)}</span>
            </div>
            <div className="pricing-row total">
              <span>Total</span>
              <span>${total.toFixed(2)}</span>
            </div>
          </div>

          {step === 'cart' && cart.length > 0 && (
            <div>
              <label style={{ fontSize: '13px', color: '#94a3b8', display: 'block', marginBottom: '8px' }}>
                Promo Code
              </label>
              <div className="coupon-box">
                <input
                  id="coupon"
                  type="text"
                  className="form-input"
                  placeholder="SAVE10"
                  value={coupon}
                  onChange={(e) => setCoupon(e.target.value)}
                />
                <button
                  className="btn coupon-btn"
                  onClick={handleApplyCoupon}
                  id="btn-apply-coupon"
                >
                  Apply
                </button>
              </div>
              {isCouponApplied && <div className="coupon-success">10% discount applied!</div>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
