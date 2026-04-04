import { NextResponse } from 'next/server';
import axios from 'axios';

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.get('query');

  if (!query) {
    return NextResponse.json({ error: 'Query is required' }, { status: 400 });
  }

  try {
    // Log the credentials for debugging
    console.log('EBAY_CLIENT_ID:', process.env.EBAY_CLIENT_ID);
    console.log('EBAY_CLIENT_SECRET:', process.env.EBAY_CLIENT_SECRET);

    // Step 1: Get eBay OAuth App Token
    const authResponse = await axios.post(
      'https://api.ebay.com/identity/v1/oauth2/token',
      'grant_type=client_credentials&scope=https://api.ebay.com/oauth/api_scope',
      {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          Authorization: `Basic ${Buffer.from(
            `${process.env.EBAY_CLIENT_ID}:${process.env.EBAY_CLIENT_SECRET}`
          ).toString('base64')}`,
        },
      }
    );

    const accessToken = authResponse.data.access_token;

    // Step 2: Call eBay Browse API
    const searchResponse = await axios.get(
      `https://api.ebay.com/buy/browse/v1/item_summary/search?q=${encodeURIComponent(
        query
      )}&limit=10`,
      {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      }
    );

    // Step 3: Process the results
    const results = searchResponse.data.itemSummaries.map((item) => ({
      title: item.title,
      price: item.price.value,
      image: item.image?.imageUrl || '', // Handle cases where image is missing
      platform: 'eBay',
    }));

    // Step 4: Return the results to the frontend
    return NextResponse.json({ results });
  } catch (error) {
    console.error('Error fetching data from eBay:', error.response?.data || error.message);
    return NextResponse.json(
      { error: 'Failed to fetch data', details: error.response?.data || error.message },
      { status: 500 }
    );
  }
}